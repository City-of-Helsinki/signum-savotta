"""
FastAPI based backend for Signum-savotta signum (shelf mark) sticker printing application.
"""

import asyncio
import base64
import gzip
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import uvicorn
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Path,
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

# Configuration from environment variables
SIERRA_API_ENDPOINT = os.getenv("SIERRA_API_ENDPOINT")
SIERRA_API_CLIENT_POOL_SIZE = int(os.getenv("SIERRA_API_CLIENT_POOL_SIZE"))
SIERRA_API_CLIENT_TIMEOUT_SECONDS = int(os.getenv("SIERRA_API_CLIENT_TIMEOUT_SECONDS", default=10))
SIERRA_API_CLIENT_RETRIES = int(os.getenv("SIERRA_API_CLIENT_RETRIES", default=3))
SIERRA_API_CLIENT_KEY = os.getenv("SIERRA_API_CLIENT_KEY")
SIERRA_API_CLIENT_SECRET = os.getenv("SIERRA_API_CLIENT_SECRET")
SIERRA_UPDATE_INTERVAL_SECONDS = int(os.getenv("SIERRA_UPDATE_INTERVAL_SECONDS", default=30))
SIERRA_UPDATE_MISFIRE_GRACE_TIME_SECONDS = int(
    os.getenv("SIERRA_UPDATE_MISFIRE_GRACE_TIME_SECONDS", default=10)
)
SIERRA_UPDATE_BATCH_SIZE_LIMIT = int(os.getenv("SIERRA_UPDATE_BATCH_SIZE_LIMIT", default=20))
SIERRA_UPDATE_SET_IUSE3 = bool(os.getenv("SIERRA_UPDATE_SET_IUSE3", default=True))
SIERRA_UPDATE_SET_INVDA = bool(os.getenv("SIERRA_UPDATE_SET_INVDA", default=True))
FULL_SYNC_BATCH_SIZE = int(os.getenv("FULL_SYNC_BATCH_SIZE", 80000))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = os.getenv("DB_NAME")
LOG_LEVEL = os.getenv("LOG_LEVEL", default="DEBUG")

sierra_http_transport = httpx.HTTPTransport(retries=SIERRA_API_CLIENT_RETRIES)
sierra_http_client = httpx.Client(
    transport=sierra_http_transport,
)

logger = logging.getLogger("backend.stdout")
logger.setLevel(logging.getLevelName(LOG_LEVEL))
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

local_timezone = ZoneInfo("localtime")

# Application name needs to be added directly to asyncpg connect() via connect_args
# Issue: https://github.com/MagicStack/asyncpg/issues/798
engine = create_async_engine(
    URL.create(
        drivername="postgresql+asyncpg",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    ),
    connect_args={"server_settings": {"application_name": "signum-savotta-backend"}},
    echo=False,
)


scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    executors={"default": AsyncIOExecutor()},
    job_defaults={"coalesce": True, "max_instances": 1},
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

    scheduler.add_job(
        send_to_sierra,
        "interval",
        id="send_to_sierra",
        replace_existing=True,
        seconds=SIERRA_UPDATE_INTERVAL_SECONDS,
        misfire_grace_time=SIERRA_UPDATE_MISFIRE_GRACE_TIME_SECONDS,
    )
    scheduler.start()

    yield
    await engine.dispose()
    scheduler.remove_job("send_to_sierra")
    scheduler.shutdown(wait=False)


async def send_to_sierra():
    """
    Sends a batch of SierraItem records to the Sierra API for updates.
    Called from backgroudtask scheduled by APScheduler.

    This function performs the following steps:
    1. Queries the database for SierraItem records that are marked for update (`in_update_queue == True`).
    2. Limits the batch size based on the `SIERRA_UPDATE_BATCH_SIZE_LIMIT` to avoid overloading the API.
    3. Authenticates with the Sierra API using Basic Auth and retrieves an access token.
    4. Iterates through each item and:
       - Fetches the current `fixedFields` from the Sierra API.
       - Optionally updates specific fields (`IUSE3` and `INVDA`) based on configuration flags.
       - Sends the updated fields back to the Sierra API using a PUT request.
    5. Logs any errors encountered during the update process.

    Notes:
    ------
    - Uses asynchronous SQLAlchemy sessions and HTTPX for non-blocking I/O.
    - Encodes client credentials using Base64 for Basic Auth.

    Exceptions:
    -----------
    - Any exceptions during API communication or data processing are caught and logged,
      including the item record ID for traceability.

    Dependencies:
    -------------
    - `SIERRA_API_CLIENT_KEY`, `SIERRA_API_CLIENT_SECRET`, `SIERRA_API_ENDPOINT`
    - `SIERRA_UPDATE_BATCH_SIZE_LIMIT`, `SIERRA_UPDATE_SET_IUSE3`, `SIERRA_UPDATE_SET_INVDA`
    - `sierra_http_client`, `logger`, `async_sessionmaker`, `engine`, `SierraItem`

    Returns:
    --------
    None
    """
    start_time = time.time()
    async with async_sessionmaker(engine)() as session:
        async with session.begin():
            stmt = select(SierraItem).where(SierraItem.in_update_queue == True)  # noqa: E712
            if SIERRA_UPDATE_BATCH_SIZE_LIMIT > 0:
                stmt = stmt.limit(SIERRA_UPDATE_BATCH_SIZE_LIMIT)
            result = await session.execute(stmt)
            items = result.scalars().all()
            base64_encoded_key_and_secret = base64.b64encode(
                f"{SIERRA_API_CLIENT_KEY}:{SIERRA_API_CLIENT_SECRET}".encode("utf-8")
            ).decode("utf-8")
            authorization_header = f"Basic {base64_encoded_key_and_secret}"
            try:
                response: httpx.Response = sierra_http_client.post(
                    url=f"{SIERRA_API_ENDPOINT}/token",
                    headers={"Authorization": authorization_header},
                )
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Error {e} while getting Sierra access token.")
            access_token = response.json()["access_token"]
            updated = 0
            for item in items:
                try:
                    try:
                        response = sierra_http_client.get(
                            url=f"{SIERRA_API_ENDPOINT}/items/{item.item_number}?fields=fixedFields",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        raise RuntimeError(f"Sierra item get failed {e}")
                    fetched_fixed_fields = response.json()["fixedFields"]
                    fixed_fields = {}
                    json = {}
                    if SIERRA_UPDATE_SET_IUSE3:
                        label = (
                            fetched_fixed_fields["93"]["label"]
                            if fetched_fixed_fields.get("93")
                            else ""
                        )
                        fixed_fields["93"] = {"label": label, "value": "1"}
                        json["fixedFields"] = fixed_fields
                    if SIERRA_UPDATE_SET_INVDA:
                        json["inventoryDate"] = (
                            datetime.now(timezone.utc)
                            .replace(microsecond=0)
                            .isoformat()
                            .replace("+00:00", "Z")
                        )
                    try:
                        response = sierra_http_client.put(
                            json=json,
                            url=f"{SIERRA_API_ENDPOINT}/items/{item.item_number}",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        raise RuntimeError(
                            f"Sierra item put failed {e.request.content.decode("utf-8")}"
                        )
                    result = await session.execute(
                        update(SierraItem)
                        .where(SierraItem.item_record_id == item.item_record_id)
                        .values({"in_update_queue": False})
                        .returning(SierraItem)
                    )
                    updated_rows = result.scalars().all()
                    if len(updated_rows) == 1:
                        updated = updated + 1
                    else:
                        raise ValueError(
                            f"Update with item number yielded {len(updated_rows)} results. Should always be 1."
                        )
                except Exception as e:
                    logger.error(f"Error {e} while updating Sierra item number {item.item_number}")
                    pass
            logger.info(
                f"Sierra update finished in {time.time() - start_time} seconds. Updated {updated} item records"
            )


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

    if client is None:
        raise HTTPException(status_code=403, detail="Invalid x-api-key")
    elif client.client_type != ClientType.ETL:
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

    if client is None:
        raise HTTPException(status_code=403, detail="Invalid x-api-key")
    elif client.client_type != ClientType.SIGNUM_PRINTER:
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
        ..., title="The barcode of the item to retrieve", pattern=r"^[0-9]{14,16}\w{0,1}$"
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


@app.put(
    "/itemdata/{barcode}",
    tags=["item"],
    dependencies=[Depends(allow_printer_client_only)],
)
async def put_item_data(
    barcode: str = Path(
        ..., title="The barcode of the item to update", pattern=r"^[0-9]{14,16}\w{0,1}$"
    )
):
    """
    Marks a SierraItem record for update by setting its `in_update_queue` flag to True.

    This endpoint is intended to be called by authorized printer clients to signal that
    an item identified by its barcode should be updated in Sierra via a background process.

    Parameters:
    -----------
    barcode : str
        The barcode of the item to be marked for update. Must match the pattern:
        14–16 digits optionally followed by one alphanumeric character.

    Behavior:
    ---------
    - Executes an asynchronous SQLAlchemy `UPDATE` statement to set `in_update_queue = True`
      for the matching SierraItem.
    - Uses `.returning()` to confirm whether any rows were affected.
    - Returns HTTP 200 with `{"updated": True}` if the item was found and updated.
    - Returns HTTP 404 with `{"updated": False}` if no matching item was found.

    Security:
    ---------
    - Access is restricted to clients authorized via the `allow_printer_client_only` dependency.

    Returns:
    --------
    JSONResponse
        A JSON object indicating whether the update was successful.
    """

    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        async with session.begin():
            result = await session.execute(
                update(SierraItem)
                .where(SierraItem.barcode == barcode)
                .values({"in_update_queue": True})
                .returning(SierraItem)
            )
            updated_rows = result.scalars().all()
            if updated_rows:
                return JSONResponse(
                    status_code=200,
                    content={
                        "updated": True,
                    },
                )
            else:
                raise HTTPException(status_code=404, detail="Item not found")


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
