"""
FastAPI based backend for label printing solution
"""

import asyncio
import gzip
import logging
import os
import sys
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Annotated

import pandas as pd
import uvicorn
from fastapi import FastAPI, File, Path, Response, UploadFile
from models.base import Base
from models.sierra_item import SierraItem
from schemas import sierra_item_schema
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

logger = logging.getLogger("feedgen.stdout")
logger.setLevel(logging.getLevelName(os.getenv("LOG_LEVEL", default="DEBUG")))
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


engine = create_async_engine(
    (
        f"postgresql+asyncpg://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}"
        f"@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}"
    ),
    echo=False,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI app lifecycle handling
    """
    created = False
    while not created:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
            created = True
        except Exception as e:
            logger.error(e)
            await asyncio.sleep(10)

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
    get_status
    """
    return {"status": "OK"}


@app.get("/readiness", tags=["readiness"])
async def get_readiness():
    """
    get_readiness
    """
    return Response(status_code=200)


@app.get("/healthz", tags=["healthz"])
async def get_healthz():
    """
    get_healthz
    """
    return Response(status_code=200)


@app.get("/itemdata/{barcode}", response_model=sierra_item_schema.SierraItem, tags=["itemdata"])
async def get_item_data(
    barcode: str = Path(
        ..., title="The ID of the item to retrieve", pattern="^[0-9]{14,16}\\w{0,1}$"
    )
):
    """
    get_item_data
    """
    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        async with session.begin():
            result = await session.execute(select(SierraItem).where(SierraItem.barcode == barcode))
            sierra_item = result.scalars().first()
            session.expunge_all()
            return sierra_item


@app.get("/sync")
async def get_sync_configuration():
    """
    get_sync_configuration
    """
    last_synced_id = 0
    async with async_sessionmaker(autocommit=False, bind=engine)() as session:
        stmt = select(func.max(SierraItem.item_record_id))
        result = await session.execute(stmt)
        last_synced_id = result.scalar()
        if last_synced_id is None:
            last_synced_id = 0
        logger.info(f"Last synced updated to {last_synced_id} ETL")

        return {"last_synced_id": last_synced_id, "batch_size": 20000}


def split_dicts_into_batches(dict_list, fields_per_dict=13, max_fields_per_batch=32767):
    """
    split_dicts_into_batches is used to
    """
    max_dicts_per_batch = max_fields_per_batch // fields_per_dict
    return [
        dict_list[i : i + max_dicts_per_batch]
        for i in range(0, len(dict_list), max_dicts_per_batch)
    ]


@app.post("/sync")
async def post_data_sync_batch(file: Annotated[UploadFile, File()]):
    """
    post_data_sync_batch
    """
    logger.info(f"Received: {file.content_type}, size {file.size}")
    file_content = await file.read()
    decompressed = gzip.decompress(file_content)

    df = pd.read_csv(BytesIO(decompressed), delimiter="\t", header=0, encoding="utf8")
    df = df.astype(
        {
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
        }
    )
    sierra_items = df.to_dict(orient="records")

    try:
        async with async_sessionmaker(autocommit=False, bind=engine)() as session:
            async with session.begin():
                batches = split_dicts_into_batches(
                    sierra_items, fields_per_dict=13, max_fields_per_batch=32767
                )
                for batch in batches:
                    stmt = insert(SierraItem).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[SierraItem.item_record_id],
                        set_={
                            col.name: stmt.excluded[col.name]
                            for col in SierraItem.__table__.columns
                            if col.name != "item_record_id"
                        },
                    ).returning(SierraItem)

                    orm_stmt = (
                        select(SierraItem)
                        .from_statement(stmt)
                        .execution_options(populate_existing=True)
                    )

                    await session.execute(orm_stmt)
                await session.commit()
    except Exception as e:
        logger.error(e)

    return {"upserted": len(sierra_items)}


log_config = uvicorn.config.LOGGING_CONFIG
log_config["formatters"]["default"]["fmt"] = log_formatter._fmt
log_config["formatters"]["access"]["fmt"] = log_formatter._fmt


config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_config=log_config, workers=4)
server = uvicorn.Server(config=config)


if __name__ == "__main__":
    server.run()
