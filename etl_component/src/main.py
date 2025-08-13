"""
Scheduled ETL task to preload item data from SierraDNA database to signum label printing backend
"""

import asyncio
import gzip
import logging
import os
import sys
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import BigInteger, bindparam, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# FIXME: Add Sentry

# Configuration from environment variables
BACKEND_URL = os.getenv("BACKEND_URL")
ETL_CLIENT_API_KEY = os.getenv("ETL_CLIENT_API_KEY")
SYNC_JOB_INTERVAL_SECONDS = int(os.getenv("SYNC_JOB_INTERVAL_SECONDS", 30))
SYNC_JOB_MISFIRE_GRACE_TIME_SECONDS = int(os.getenv("SYNC_JOB_MISFIRE_GRACE_TIME_SECONDS", 30))
MAX_SYNC_DELTA_MINUTES = int(os.getenv("MAX_SYNC_DELTA_MINUTES", 60))
LOG_LEVEL = os.getenv("LOG_LEVEL", default="DEBUG")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = os.getenv("DB_NAME")

logger = logging.getLogger("etl.stdout")
logger.setLevel(logging.getLevelName(LOG_LEVEL))
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

local_timezone = ZoneInfo("localtime")

full_sync_sql_query = """WITH
item AS (
    SELECT
        record_id,
        itype_code_num
    FROM
        sierra_view.item_record
    WHERE
        record_id > :last_synced_id
    ORDER BY
        record_id
    LIMIT :batch_size
),
item_number AS (
    SELECT
        id,
        record_last_updated_gmt as item_record_last_updated_gmt,
        record_num as item_number
    FROM sierra_view.record_metadata
    WHERE record_type_code = 'i'
    AND id IN (SELECT item.record_id FROM item)
),
itype_property_myuser AS (
    SELECT
        name, code
    FROM
        sierra_view.itype_property_myuser
),
item_record_property AS (
    SELECT
        item_record_id,
        barcode
    FROM
        sierra_view.item_record_property
    WHERE
        item_record_id IN (SELECT item.record_id FROM item)
),
bib_item_link AS (
    SELECT
        bib_record_id,
        item_record_id
    FROM
        sierra_view.bib_record_item_record_link
    WHERE
        item_record_id IN (SELECT item.record_id FROM item)
),
bib_number AS (
    SELECT
        id,
        record_last_updated_gmt as bib_record_last_updated_gmt,
        record_num as bib_number
    FROM sierra_view.record_metadata
    WHERE record_type_code = 'b'
    AND id IN (SELECT bib_item_link.bib_record_id FROM bib_item_link)
),
bib_record_property AS (
    SELECT
        bib_record_id, best_author, best_title, material_code
    FROM
        sierra_view.bib_record_property
    WHERE
        bib_record_id IN (SELECT bib_item_link.bib_record_id from bib_item_link)
),
material_property_myuser AS (
    SELECT
        code, name
    FROM
        sierra_view.material_property_myuser
),
raw_subfields AS (
    SELECT
        record_id,
        json_agg(
            json_build_object(
                'marc_tag', marc_tag,
                'marc_ind1', marc_ind1,
                'marc_ind2', marc_ind2,
                'field_type_code', field_type_code,
                'tag', tag,
                'content', content
            )
        ) AS shelfmark_json
    FROM sierra_view.subfield
    WHERE
        (marc_tag = '100' OR marc_tag = '110' OR marc_tag = '111' OR marc_tag = '130' OR marc_tag = '245')
        AND record_id IN (SELECT bib_item_link.bib_record_id from bib_item_link)
    GROUP BY record_id
    ORDER BY record_id ASC
),
classification AS (
    SELECT
        record_id,
        MAX(content) AS classification
    FROM sierra_view.subfield
    WHERE
        marc_tag = '097'
        AND record_id IN (SELECT bib_item_link.bib_record_id from bib_item_link)
    GROUP BY record_id
    ORDER BY record_id ASC
)
SELECT
    item.record_id AS item_record_id,
    item_number.item_number,
    item_record_property.barcode,
    bib_record_property.bib_record_id,
    bib_number.bib_number,
    bib_record_property.best_author,
    bib_record_property.best_title,
    item.itype_code_num,
    itype_property_myuser.name as item_type_name,
    bib_record_property.material_code,
    material_property_myuser.name as material_name,
    classification.classification,
    raw_subfields.shelfmark_json
FROM
    item
LEFT JOIN item_number ON item.record_id = item_number.id
LEFT JOIN item_record_property ON item.record_id = item_record_property.item_record_id
LEFT JOIN itype_property_myuser ON item.itype_code_num = itype_property_myuser.code
LEFT JOIN bib_item_link ON item.record_id = bib_item_link.item_record_id
LEFT JOIN bib_number ON bib_item_link.bib_record_id = bib_number.id
LEFT JOIN bib_record_property ON bib_item_link.bib_record_id = bib_record_property.bib_record_id
LEFT JOIN material_property_myuser ON bib_record_property.material_code = material_property_myuser.code
LEFT JOIN classification ON classification.record_id = bib_item_link.bib_record_id
LEFT JOIN raw_subfields ON raw_subfields.record_id = bib_item_link.bib_record_id
ORDER BY item_record_id"""


updated_on_or_after_timestamp_sql_query = """WITH
updated AS (
    SELECT
        id, record_type_code, record_num
    FROM
        sierra_view.record_metadata
    WHERE
        record_last_updated_gmt AT TIME ZONE current_setting('timezone') >= :timestamp
    AND (record_type_code = 'b' OR record_type_code = 'i')
),
bib_item_link AS (
    SELECT
        item_record_id,
        MAX(bib_record_id) AS bib_record_id
    FROM
        sierra_view.bib_record_item_record_link
    WHERE
        item_record_id IN (SELECT id FROM updated WHERE record_type_code = 'i')
        OR bib_record_id IN (SELECT id FROM updated WHERE record_type_code = 'b')
    GROUP BY
        item_record_id
    ORDER BY
        item_record_id
),
item_record_property AS (
    SELECT
        item_record_id,
        barcode
    FROM
        sierra_view.item_record_property
    WHERE
        item_record_id IN (SELECT bib_item_link.item_record_id FROM bib_item_link)
),
item AS (
    SELECT
        record_id,
        itype_code_num
    FROM
        sierra_view.item_record
    WHERE
        record_id IN (SELECT bib_item_link.item_record_id FROM bib_item_link)
),
itype_property_myuser AS (
    SELECT
        name, code
    FROM
        sierra_view.itype_property_myuser
),
bib_record_property AS (
    SELECT
        bib_record_id, best_author, best_title, material_code
    FROM
        sierra_view.bib_record_property
    WHERE
        bib_record_id IN (SELECT bib_item_link.bib_record_id from bib_item_link)
),
material_property_myuser AS (
    SELECT
        code, name
    FROM
        sierra_view.material_property_myuser
),
raw_subfields AS (
    SELECT
        record_id,
        json_agg(
            json_build_object(
                'marc_tag', marc_tag,
                'marc_ind1', marc_ind1,
                'marc_ind2', marc_ind2,
                'field_type_code', field_type_code,
                'tag', tag,
                'content', content
            )
        ) AS shelfmark_json
    FROM sierra_view.subfield
    WHERE
        (marc_tag = '100' OR marc_tag = '110' OR marc_tag = '111' OR marc_tag = '130' OR marc_tag = '245')
        AND record_id IN (SELECT bib_item_link.bib_record_id from bib_item_link)
    GROUP BY record_id
    ORDER BY record_id ASC
),
classification AS (
    SELECT
        record_id,
        MAX(content) AS classification
    FROM sierra_view.subfield
    WHERE
        marc_tag = '097'
        AND record_id IN (SELECT bib_item_link.bib_record_id from bib_item_link)
    GROUP BY record_id
    ORDER BY record_id ASC
),
item_number AS (
    SELECT id, record_num as item_number
    FROM sierra_view.record_metadata
    WHERE record_type_code = 'i'
    AND id IN (SELECT bib_item_link.item_record_id FROM bib_item_link)
),
bib_number AS (
    SELECT id, record_num as bib_number
    FROM sierra_view.record_metadata
    WHERE record_type_code = 'b'
    AND id IN (SELECT bib_item_link.bib_record_id FROM bib_item_link)
)

SELECT
    bib_item_link.item_record_id,
    item_number.item_number,
    item_record_property.barcode,
    bib_item_link.bib_record_id,
    bib_number.bib_number,
    bib_record_property.best_author,
    bib_record_property.best_title,
    item.itype_code_num,
    itype_property_myuser.name as item_type_name,
    bib_record_property.material_code,
    material_property_myuser.name as material_name,
    classification.classification,
    raw_subfields.shelfmark_json
FROM
    bib_item_link
LEFT JOIN item_record_property ON bib_item_link.item_record_id = item_record_property.item_record_id
LEFT JOIN item ON item.record_id = bib_item_link.item_record_id
LEFT JOIN itype_property_myuser ON item.itype_code_num = itype_property_myuser.code
LEFT JOIN bib_record_property ON bib_item_link.bib_record_id = bib_record_property.bib_record_id
LEFT JOIN material_property_myuser ON bib_record_property.material_code = material_property_myuser.code
LEFT JOIN classification ON classification.record_id = bib_item_link.bib_record_id
LEFT JOIN raw_subfields ON raw_subfields.record_id = bib_item_link.bib_record_id
LEFT JOIN item_number ON bib_item_link.item_record_id = item_number.id
LEFT JOIN bib_number ON bib_item_link.bib_record_id = bib_number.id
WHERE
    bib_item_link.item_record_id IS NOT NULL
    AND bib_item_link.bib_record_id IS NOT NULL
"""


# Scheduled task
async def task():
    """
    task
    """
    engine = None
    try:
        config = None
        dataframe = None
        session_began: datetime | None = None
        # FIXME: Handling HTTP timeouts and unreachable Sierra DB gracefully.
        async with httpx.AsyncClient(
            timeout=4.0, headers={"x-api-key": ETL_CLIENT_API_KEY}
        ) as client:
            try:
                config_response = await client.get(f"{BACKEND_URL}/sync")
                config_response.raise_for_status()
                config = config_response.json()
                logger.info(f"syncing with config: {config}")
                if config.get("sync_status") == "processing_sync_batch":
                    logger.warning(
                        "Target is still processing previous sync batch. Stopping task instance."
                    )
                    return
                elif config.get("sync_type") == "SYNC_FULL":
                    try:
                        int(config.get("last_synced_id"))
                        int(config.get("batch_size"))
                    except Exception:
                        logger.error(
                            (
                                "SYNC_FULL with faulty parameters: "
                                f"last_synced_id: {config.get("last_synced_id")}, "
                                f"batch_size: {config.get("batch_size")}"
                            )
                        )
                        return
                elif config.get("sync_type") == "SYNC_CHANGES":
                    try:
                        datetime.fromisoformat(config.get("timestamp"))
                    except Exception:
                        logger.error(
                            (
                                "SYNC_CHANGES with faulty parameters: "
                                f"timestamp: {config.get("timestamp")}"
                            )
                        )
                        return
            except Exception as e:
                logger.error(f"Error fetching configuration {e}.")
                return
        if config is not None:
            engine = create_async_engine(
                URL.create(
                    drivername="postgresql+asyncpg",
                    username=DB_USER,
                    password=DB_PASSWORD,
                    host=DB_HOST,
                    port=DB_PORT,
                    database=DB_NAME,
                ),
                connect_args={"server_settings": {"application_name": "signum-savotta-etl"}},
                echo=False,
            )
            async with async_sessionmaker(autocommit=False, bind=engine)() as session:
                async with session.begin():
                    try:
                        result = await session.execute(func.current_setting("timezone"))
                        db_timezone = ZoneInfo(result.scalar_one())

                        result = await session.execute(select(func.now()))
                        session_began = result.scalar_one()

                        logger.info(
                            f"Sync db session began at: {session_began}, DB timezone: {db_timezone}"
                        )

                        result = None
                        if config.get("sync_mode") == "SYNC_FULL":
                            result = await session.execute(
                                text(full_sync_sql_query).bindparams(
                                    bindparam(
                                        "last_synced_id",
                                        value=config.get("last_synced_id"),
                                        type_=BigInteger,
                                    ),
                                    bindparam("batch_size", value=config.get("batch_size")),
                                )
                            )
                        elif config.get("sync_mode") == "SYNC_CHANGES":
                            requested = datetime.fromisoformat(config.get("timestamp")).astimezone(
                                db_timezone
                            )
                            safedelta = session_began - timedelta(minutes=MAX_SYNC_DELTA_MINUTES)
                            if requested < safedelta:
                                logger.warning(
                                    (
                                        f"Requested changes since {requested}. "
                                        f"In order to avoid slow query, only changes after {safedelta} are provided."
                                    )
                                )
                                timestamp = safedelta
                            else:
                                timestamp = requested
                            result = await session.execute(
                                text(updated_on_or_after_timestamp_sql_query).bindparams(
                                    bindparam("timestamp", value=timestamp)
                                )
                            )
                        if result is not None:
                            dataframe = pd.DataFrame(
                                result.fetchall(),
                                columns=result.keys(),
                            )
                            # FIXME: The dtypes should be in a common library shared between backend and etl
                            dataframe = dataframe.astype(
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
                                    "shelfmark_json": "string",
                                }
                            )
                    except Exception as e:
                        {logger.error(e)}
                    await session.close()
            if dataframe is not None:
                tsv_buffer = StringIO()
                dataframe.to_csv(tsv_buffer, sep="\t", index=False)
                tsv_buffer.seek(0)
                files = {
                    "file": (
                        "data.tsv.gz",
                        gzip.compress(tsv_buffer.getvalue().encode("utf-8")),
                        "application/gzip",
                    )
                }
                async with httpx.AsyncClient(
                    timeout=120.0, headers={"x-api-key": ETL_CLIENT_API_KEY}
                ) as client:
                    try:
                        post_response = await client.post(
                            f"{BACKEND_URL}/sync",
                            data={"timestamp": session_began.isoformat()},
                            files=files,
                        )
                        post_response.raise_for_status()
                        logger.info(f"{post_response.json()}")
                    except Exception as e:
                        logger.exception(f"Error uploading sync batch: {e}")
                await engine.dispose()
            else:
                logger.error("Dataframe was not populated")
        else:
            logger.error("Empty configuration")
    except Exception as e:
        if engine:
            await engine.dispose()
        logger.exception(f"Error during task: {e}")


async def main():
    """
    main
    """
    scheduler = AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_job(
        task,
        "interval",
        seconds=SYNC_JOB_INTERVAL_SECONDS,
        misfire_grace_time=SYNC_JOB_MISFIRE_GRACE_TIME_SECONDS,
    )
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)

    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
