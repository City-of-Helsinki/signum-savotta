"""
FastAPI based backend for Signum-savotta signum (shelf mark) sticker printing application.
"""

import asyncio
import gzip
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from typing import Annotated
from zoneinfo import ZoneInfo

import pandas as pd
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from models.backend_state import BackendState, SyncMode
from models.base import Base
from models.client import Client, ClientType
from models.sierra_item import SierraItem
from schemas import sierra_item_schema
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.inspection import inspect

logger = logging.getLogger("backend.stdout")
logger.setLevel(logging.getLevelName(os.getenv("LOG_LEVEL", default="DEBUG")))
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

FULL_SYNC_BATCH_SIZE = int(os.getenv("FULL_SYNC_BATCH_SIZE", 80000))

local_timezone = ZoneInfo("localtime")

# Application name needs to be added directly to asyncpg connect() via connect_args
# Issue: https://github.com/MagicStack/asyncpg/issues/798
engine = create_async_engine(
    URL.create(
        drivername="postgresql+asyncpg",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
    ),
    connect_args={"server_settings": {"application_name": "signum-savotta-backend"}},
    echo=False,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI application lifespan handler.

    - Waits for the database to become available.
    - Creates tables if they don't exist.
    - Initializes persistent backend state if missing.
    """
    database_available = False
    max_retries = 30
    retries = 0
    while not database_available and retries < max_retries:
        try:
            async with engine.begin() as conn:
                # await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                database_available = True
        except Exception as e:
            retries += 1
            logger.error(e)
            await asyncio.sleep(10)

    if not database_available:
        raise RuntimeError("Database not available after multiple attempts.")

    async with async_sessionmaker(engine)() as session:
        async with session.begin():
            result = await session.execute(select(BackendState))
            backend_state: BackendState = result.scalar_one_or_none()
            if not backend_state:
                initial_state = BackendState(
                    initialized_at=datetime.now(local_timezone), sync_mode=SyncMode.SYNC_FULL
                )
                backend_state = await BackendState.upsert_singleton(
                    session=session, instance=initial_state
                )
                logger.info("Initialized persistent backend state.")
            state_str = ", ".join(
                f"{attr.key}: {getattr(backend_state, attr.key)}"
                for attr in inspect(BackendState).attrs
            )
            logger.info(("Persistent backend state: " f"{state_str}"))
    yield
    await engine.dispose()


async def allow_any_valid_client(x_api_key: Annotated[str, Header()]):
    """
    Validates the provided `x-api-key` header and returns the corresponding Client object.

    This dependency checks whether the API key exists in the database. If valid, it returns
    the associated Client instance. If invalid or missing, it raises an HTTP 403 error.

    Args:
        x_api_key (str): The API key provided in the request header.

    Returns:
        Client: The validated client object.

    Raises:
        HTTPException: If the API key is missing or invalid.
    """

    client: Client | None = None
    async with async_sessionmaker(engine)() as session:
        async with session.begin():
            stmt = select(Client).where(Client.api_key == f"{x_api_key}")
            result = await session.execute(stmt)
            client = result.scalar_one_or_none()
            session.expunge_all()
    if client is None:
        raise HTTPException(status_code=403, detail="Invalid x-api-key")
    else:
        return client


async def allow_etl_client_only(client: Annotated[Client, Depends(allow_any_valid_client)]):
    """
    Ensures that the validated client is of type `ETL`.

    This dependency builds on `allow_any_valid_client` and restricts access to clients
    whose `client_type` is `ClientType.ETL`. If the client type does not match, it raises
    an HTTP 403 error.

    Args:
        client (Client): The validated client object from the previous dependency.

    Returns:
        Client: The client object if it is of type ETL.

    Raises:
        HTTPException: If the client is not of type ETL.
    """

    if client.client_type != ClientType.ETL:
        raise HTTPException(status_code=403, detail="Invalid x-api-key")
    else:
        return client


async def allow_printer_client_only(client: Annotated[Client, Depends(allow_any_valid_client)]):
    """
    Ensures that the validated client is of type `SIGNUM_PRINTER`.

    This dependency builds on `allow_any_valid_client` and restricts access to clients
    whose `client_type` is `ClientType.SIGNUM_PRINTER`. If the client type does not match,
    it raises an HTTP 403 error.

    Args:
        client (Client): The validated client object from the previous dependency.

    Returns:
        Client: The client object if it is of type SIGNUM_PRINTER.

    Raises:
        HTTPException: If the client is not of type SIGNUM_PRINTER.
    """

    if client.client_type != ClientType.SIGNUM_PRINTER:
        raise HTTPException(status_code=403, detail="Invalid x-api-key")
    else:
        return client


app = FastAPI(
    lifespan=lifespan,
    root_path="/",
    title="Signum-savotta API",
    description="API for Signum-savotta signum (shelf mark) sticker printing application.",
    docs_url="/",
    redoc_url="/redoc",
    version="1.0.0",
)


@app.get("/readiness", tags=["readiness"])
async def get_readiness():
    """
    Readiness probe endpoint for Kubernetes readiness probes.
    Returns 200 if the app is ready to serve traffic, 503 otherwise.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return Response(status_code=200)
    except Exception:
        return Response(status_code=503)


@app.get("/healthz", tags=["healthz"])
async def get_healthz():
    """
    General health check to confirm the app is alive for Kubernetes liveness probes or external monitoring tools.
    Always returns 200 OK
    """
    return Response(status_code=200)


@app.post("/status", tags=["status"])
async def post_status(
    internal_hostname: Annotated[str, Form()],
    internal_ip_address: Annotated[str, Form()],
    client: Annotated[Client, Depends(allow_printer_client_only)],
):
    """
    This endpoint is intended for authorized printer clients to report their internal
    hostname and IP address. It updates the client's `last_seen_at`, `internal_hostname`,
    and `internal_ip_address` fields in the database. In response, it returns the current
    backend synchronization state.

    Args:
        internal_hostname (str): The hostname of the client machine.
        internal_ip_address (str): The internal IP address of the client.
        client (Client): The authenticated client, restricted to SIGNUM_PRINTER type.

    Returns:
        JSONResponse: A JSON object containing backend synchronization state fields:
            - full_sync_completed_at
            - initialized_at
            - last_sync_run_completed_at
            - sync_changes_since
            - sync_mode

    Raises:
        HTTPException: If the client is not authorized or the database operation fails.
    """

    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        async with session.begin():
            result = await session.execute(select(BackendState))
            backend_state = result.scalar_one_or_none()
            if backend_state is not None:
                content = {
                    "full_sync_completed_at": (
                        backend_state.full_sync_completed_at.isoformat()
                        if backend_state.full_sync_completed_at
                        else ""
                    ),
                    "initialized_at": (
                        backend_state.initialized_at.isoformat()
                        if backend_state.initialized_at
                        else ""
                    ),
                    "last_sync_run_completed_at": (
                        backend_state.last_sync_run_completed_at.isoformat()
                        if backend_state.last_sync_run_completed_at
                        else ""
                    ),
                    "sync_changes_since": (
                        backend_state.sync_changes_since.isoformat()
                        if backend_state.sync_changes_since
                        else ""
                    ),
                    "sync_mode": backend_state.sync_mode.name,
                }
            stmt = (
                update(Client)
                .where(Client.id == client.id)
                .values(
                    internal_hostname=internal_hostname,
                    internal_ip_address=internal_ip_address,
                    last_seen_at=datetime.now(local_timezone),
                )
            )
            await session.execute(stmt)
            await session.commit()
            return JSONResponse(status_code=200, content=content)


@app.get(
    "/itemdata/{barcode}",
    response_model=sierra_item_schema.SierraItem,
    tags=["itemdata"],
    dependencies=[Depends(allow_printer_client_only)],
)
async def get_item_data(
    barcode: str = Path(
        ..., title="The ID of the item to retrieve", pattern=r"^[0-9]{14,16}\w{0,1}$"
    )
):
    """
    This endpoint allows clients to fetch detailed information about a library item
    by providing its barcode. The barcode must be a 14 to 16-digit numeric string,
    optionally followed by a single alphanumeric character.

    ### Path Parameters:
    - **barcode** (`str`): The barcode of the item to retrieve. Must match the pattern:
      14–16 digits optionally followed by one alphanumeric character.

    ### Returns:
    - **200 OK**: A `SierraItem` object containing the item's metadata.
    - **404 Not Found**: If no item with the given barcode exists in the database.

    ### Response Model:
    - `SierraItem`

    ### Example:
    ```
    GET /itemdata/12345678901234X
    ```

    ### Tags:
    - itemdata
    """

    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        async with session.begin():
            result = await session.execute(select(SierraItem).where(SierraItem.barcode == barcode))
            sierra_item: SierraItem = result.scalar_one_or_none()
            session.expunge_all()
            if sierra_item is None:
                raise HTTPException(status_code=404, detail="Item not found")
            else:
                logger.info(f"sierra: {sierra_item.best_title}")
                return sierra_item


@app.get("/sync", tags=["sync"], dependencies=[Depends(allow_etl_client_only)])
async def get_sync_configuration():
    """
    Retrieve the current synchronization configuration and status.

    This endpoint provides insight into the backend's synchronization state, which determines
    how Sierra item data is being ingested and updated. The backend operates in two modes:

    - **SYNC_FULL**: Initial mode after startup, performing full data ingestion in batches.
    - **SYNC_CHANGES**: Incremental mode after full sync is completed, ingesting only changes.

    ### Returns:
    - **200 OK**: A JSON object containing:
        - `sync_mode`: Current synchronization mode (`SYNC_FULL` or `SYNC_CHANGES`)
        - `batch_size`: (Only in `SYNC_FULL`) Number of items per batch
        - `last_synced_id`: (Only in `SYNC_FULL`) Highest item record ID processed
        - `timestamp`: (Only in `SYNC_CHANGES`) ISO 8601 timestamp of last changes processed

    ### Error Handling:
    - **500 Internal Server Error**: If the backend state is invalid or cannot be interpreted.

    ### Example Response (SYNC_FULL):
    ```json
    {
      "sync_mode": "SYNC_FULL",
      "batch_size": 1000,
      "last_synced_id": 123456
    }
    ```

    ### Example Response (SYNC_CHANGES):
    ```json
    {
      "sync_mode": "SYNC_CHANGES",
      "timestamp": "2025-07-28T12:00:00+03:00"
    }
    ```
    """
    last_synced_id = 0
    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        async with session.begin():
            result = await session.execute(select(BackendState))
            backend_state: BackendState = result.scalar_one()
            if backend_state.sync_mode == SyncMode.SYNC_FULL:
                result = await session.execute(select(func.max(SierraItem.item_record_id)))
                last_synced_id = result.scalar_one_or_none()
                if last_synced_id is None:
                    last_synced_id = 0
                logger.info(
                    (
                        f"{backend_state.sync_mode} with batch_size: "
                        f"{FULL_SYNC_BATCH_SIZE}, last_synced_id: {last_synced_id}"
                    )
                )
                return JSONResponse(
                    status_code=200,
                    content={
                        "sync_mode": backend_state.sync_mode.name,
                        "batch_size": FULL_SYNC_BATCH_SIZE,
                        "last_synced_id": last_synced_id,
                    },
                )
            elif backend_state.sync_mode == SyncMode.SYNC_CHANGES:
                logger.info(
                    f"{backend_state.sync_mode} with timestamp: {backend_state.sync_changes_since}"
                )
                return JSONResponse(
                    status_code=200,
                    content={
                        "sync_mode": backend_state.sync_mode.name,
                        "timestamp": backend_state.sync_changes_since.isoformat(),
                    },
                )
            else:
                state_str = ", ".join(
                    f"{attr.key}: {getattr(backend_state, attr.key)}"
                    for attr in inspect(BackendState).attrs
                )
                raise HTTPException(
                    status_code=500,
                    detail=("Error fetching sync configuration, state: " f"{state_str}"),
                )


@app.post("/sync", tags=["sync"], dependencies=[Depends(allow_etl_client_only)])
async def post_data_sync_batch(
    file: Annotated[UploadFile, File()], timestamp: Annotated[datetime, Form()]
):
    """
    Ingest and synchronize Sierra item data from a gzip-compressed TSV file.

    This endpoint accepts a gzipped TSV file containing Sierra item records along with
    an ETL timestamp. It decompresses and parses the file, upserts the item data into
    the database, and updates the backend synchronization state based on the current
    sync mode.

    ### Form Data:
    - **file** (`UploadFile`): A gzip-compressed TSV file containing Sierra item data.
    - **timestamp** (`datetime`): ISO 8601 formatted timestamp representing the ETL run time.

    ### File Format:
    The TSV file must include the following columns:
    - `item_record_id`, `item_number`, `barcode`, `bib_number`, `bib_record_id`,
      `best_author`, `best_title`, `itype_code_num`, `item_type_name`, `material_code`,
      `material_name`, `classification`, `shelfmark_json`

    ### Behavior:
    - Parses the file into a DataFrame with strict typing.
    - Upserts item records into the database.

    ### Returns:
    - **200 OK**: JSON object with the number of upserted items.
    - **400 Bad Request**: If the uploaded file is not a valid gzip file.
    - **500 Internal Server Error**: For unexpected errors during processing.

    ### Example:
    ```
    POST /sync
    Content-Type: multipart/form-data
    Form fields:
      - file: items.tsv.gz
      - timestamp: 2025-07-28T12:00:00+03:00
    ```

    ### Response:
    ```json
    {
      "upserted": 1245
    }
    ```
    """
    try:

        logger.info(f"Received: {file.content_type}, size {file.size}. ETL timestamp: {timestamp}")
        file_content = await file.read()
        decompressed = gzip.decompress(file_content)

        df = pd.read_csv(
            BytesIO(decompressed),
            delimiter="\t",
            header=0,
            encoding="utf8",
            # FIXME: The dtypes should be in a common library shared between backend and etl
            dtype={
                "item_record_id": "Int64",
                "item_number": "string",
                "barcode": "string",
                "bib_number": "string",
                "bib_record_id": "Int64",
                "best_author": "string",
                "best_title": "string",
                "itype_code_num": "uint8",
                "item_type_name": "string",
                "material_code": "string",
                "material_name": "string",
                "classification": "string",
                "shelfmark_json": "string",
            },
        )
        df["updated_at"] = pd.Timestamp(timestamp)
        sierra_items = df.to_dict(orient="records")

        async with async_sessionmaker(autocommit=False, bind=engine)() as session:
            async with session.begin():
                result = await session.execute(select(BackendState))
                backend_state: BackendState = result.scalar_one()
                await SierraItem.upsert_batch(
                    session=session, dicts=sierra_items, return_upserted=False
                )
                if backend_state.sync_mode == SyncMode.SYNC_FULL:
                    first_etl = timestamp if not backend_state.sync_changes_since else None
                    if len(sierra_items) < FULL_SYNC_BATCH_SIZE:
                        await BackendState.upsert_singleton(
                            session=session,
                            instance=BackendState(
                                sync_mode=SyncMode.SYNC_CHANGES,
                                sync_changes_since=first_etl,
                                full_sync_completed_at=datetime.now(local_timezone),
                                last_sync_run_completed_at=datetime.now(local_timezone),
                            ),
                        )
                    else:
                        await BackendState.upsert_singleton(
                            session=session,
                            instance=BackendState(
                                sync_changes_since=first_etl,
                                last_sync_run_completed_at=datetime.now(local_timezone),
                            ),
                        )
                elif backend_state.sync_mode == SyncMode.SYNC_CHANGES:
                    await BackendState.upsert_singleton(
                        session=session,
                        instance=BackendState(
                            last_sync_run_completed_at=datetime.now(local_timezone),
                            sync_changes_since=timestamp,
                        ),
                    )
                else:
                    raise ValueError("Backend state error, sync_mode")
                await session.commit()
    except gzip.BadGzipFile as e:
        logger.error(f"Gzip error: {e}")
        raise HTTPException(status_code=400, detail="Invalid gzip file")
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Internal server error")
    return JSONResponse(status_code=200, content={"upserted": len(sierra_items)})


log_config = uvicorn.config.LOGGING_CONFIG
log_config["formatters"]["default"]["fmt"] = log_formatter._fmt
log_config["formatters"]["access"]["fmt"] = log_formatter._fmt


config = uvicorn.Config(
    app=app,
    host="0.0.0.0",
    port=8000,
    log_config=log_config,
    workers=4,
    timeout_keep_alive=60,
    timeout_notify=60,
    timeout_graceful_shutdown=120,
)
server = uvicorn.Server(config=config)


if __name__ == "__main__":
    server.run()
