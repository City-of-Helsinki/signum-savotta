"""
FastAPI based backend for label printing solution
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
from fastapi import FastAPI, File, Form, HTTPException, Path, Response, UploadFile
from models.backend_state import BackendState, SyncMode, SyncStatus
from models.base import Base
from models.sierra_item import SierraItem
from schemas import sierra_item_schema
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
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

FULL_SYNC_BATCH_SIZE = int(os.getenv("FULL_SYNC_BATCH_SIZE", 100000))

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
    - Logs the current backend state.
    - Disposes of the engine on shutdown.
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
                    initialized_at=datetime.now(local_timezone),
                    sync_mode=SyncMode.SYNC_FULL,
                    sync_status=SyncStatus.IDLE,
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


app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    """
    read_root
    """
    return {"message": "Welcome to the FastAPI application!"}


@app.get("/status", tags=["status"])
def get_status():
    """
    General health check to confirm the app is alive for Kubernetes liveness probes or external monitoring tools.
    """
    return {"status": "OK"}


@app.get("/readiness", tags=["readiness"])
async def get_readiness():
    """
    Readiness probe endpoint. Returns 200 if the app is ready to serve traffic, 503 otherwise.
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


@app.get("/itemdata/{barcode}", response_model=sierra_item_schema.SierraItem, tags=["itemdata"])
async def get_item_data(
    barcode: str = Path(
        ..., title="The ID of the item to retrieve", pattern="^[0-9]{14,16}\\w{0,1}$"
    )
):
    """
    Retrieve item data from the Sierra database using a barcode.

    - **barcode**: A 14–16 digit numeric string, optionally followed by one alphanumeric character.
    - **Returns**: A SierraItem object if found, otherwise `None`.
    """
    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        async with session.begin():
            result = await session.execute(select(SierraItem).where(SierraItem.barcode == barcode))
            sierra_item = result.scalar_one_or_none()
            session.expunge_all()
            if sierra_item is None:
                raise HTTPException(status_code=404, detail="Item not found")
            else:
                return sierra_item


@app.get("/sync")
async def get_sync_configuration():
    """
    Retrieve the current synchronization configuration.

    Returns sync mode, status, and either the last synced item ID (for full sync)
    or the timestamp of last changes (for incremental sync).

    The backend is in full sync mode after initial startup. When the full sync has been completed
    the backend will switch to sync changes mode.
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
                return {
                    "sync_mode": backend_state.sync_mode,
                    "sync_status": backend_state.sync_status,
                    "batch_size": FULL_SYNC_BATCH_SIZE,
                    "last_synced_id": last_synced_id,
                }
            elif backend_state.sync_mode == SyncMode.SYNC_CHANGES:
                logger.info(
                    f"{backend_state.sync_mode} with timestamp: {backend_state.sync_changes_since}"
                )
                return {
                    "sync_mode": backend_state.sync_mode,
                    "sync_status": backend_state.sync_status,
                    "timestamp": backend_state.sync_changes_since.isoformat(),
                }
            else:
                state_str = ", ".join(
                    f"{attr.key}: {getattr(backend_state, attr.key)}"
                    for attr in inspect(BackendState).attrs
                )
                logger.error(("Error fetching sync configuration, state: " f"{state_str}"))
                return {}


@app.post("/sync")
async def post_data_sync_batch(
    file: Annotated[UploadFile, File()], timestamp: Annotated[datetime, Form()]
):
    """
    Accepts a gzip-compressed TSV file containing Sierra item data and a timestamp.
    Parses and upserts the data into the database, updating sync state accordingly.

    Args:
        file: Gzipped TSV file containing item data.
        timestamp: ISO 8601 formatted ETL timestamp.

    Returns:
        JSON response with the number of upserted items or an error message.
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
                "paasana_json": "string",
            },
        )
        df["updated_at"] = pd.Timestamp(timestamp)
        sierra_items = df.to_dict(orient="records")

        async with async_sessionmaker(autocommit=False, bind=engine)() as session:
            async with session.begin():
                result = await session.execute(select(BackendState))
                backend_state: BackendState = result.scalar_one()
                await SierraItem.upsert_batch(session=session, dicts=sierra_items)
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

    return {"upserted": len(sierra_items)}


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
