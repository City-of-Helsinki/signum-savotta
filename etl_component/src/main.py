"""
Scheduled ETL task to preload item data from SierraDNA database to signum label printing backend
"""

import asyncio
import gzip
import logging
import os
import sys
from io import StringIO

import httpx
import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

logger = logging.getLogger("feedgen.stdout")
logger.setLevel(logging.getLevelName(os.getenv("LOG_LEVEL", default="DEBUG")))
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL")

sql_query = """WITH
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
    SELECT id, concat(concat('i',record_num),agency_code_num) as item_number
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
    SELECT id, concat(concat('b',record_num),agency_code_num) as bib_number
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
        ) AS paasana_json
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
    raw_subfields.paasana_json
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


# Scheduled task
async def task():
    engine = create_async_engine(
        (
            f"postgresql+asyncpg://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}"
            f"@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_DATABASE")}"
        ),
        echo=False,
    )
    try:
        async with async_sessionmaker(autocommit=False, bind=engine)() as session:
            async with httpx.AsyncClient(timeout=4.0) as client:
                config_response = await client.get(f"{BACKEND_URL}/sync")
                config = config_response.json()
                last_synced_id = config.get("last_synced_id")
                batch_size = config.get("batch_size")
                if last_synced_id is None or batch_size is None:
                    logger.error("Missing sync parameters in config response.")
                    return
            async with session.begin():
                result = await session.execute(
                    text(sql_query).bindparams(
                        bindparam("last_synced_id", value=last_synced_id),
                        bindparam("batch_size", value=batch_size),
                    )
                )
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
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
                tsv_buffer = StringIO()
                df.to_csv(tsv_buffer, sep="\t", index=False)
                tsv_buffer.seek(0)
                files = {
                    "file": (
                        "data.tsv.gz",
                        gzip.compress(tsv_buffer.getvalue().encode("utf-8")),
                        "application/gzip",
                    )
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    post_response = await client.post(f"{BACKEND_URL}/sync", files=files)
                    logger.info(f"{post_response.json()}")
                await session.close()
            await engine.dispose()
    except Exception as e:
        await engine.dispose()
        logger.exception(f"Error during task: {e}")


# Main entry point
async def main():
    scheduler = AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_job(task, "interval", seconds=30)
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)  # Keeps the loop alive

    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
