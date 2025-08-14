# ETL Component

The ETL component is responsible for periodically synchronizing Sierra LMS item data with the backend database for the Signum-savotta solution. It is stateless, and fetches configuration from the backend for each run.

## Features

- **Periodic Data Synchronization:** Fetches item data from Sierra LMS at configurable intervals.
- **REST API Integration:** Communicates with the backend via FastAPI endpoints.
- **Error Handling & Logging:** Robust error reporting and logging using Sentry and standard logging.
- **Configurable:** All connection and sync parameters are set via environment variables.

## Requirements

- Python 3.10+
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [Pandas](https://pandas.pydata.org/)
- [httpx](https://www.python-httpx.org/)
- [sentry-sdk](https://pypi.org/project/sentry-sdk/)
- [Uvicorn](https://www.uvicorn.org/)

## Usage

Intended to be run using docker-compose locally or installed to a server.

## Periodic Data Synchronization Flow

```mermaid
flowchart TD
    A["`
    APScheduler starts the periodic job
    `"] --> B["`
    Wait job start until interval configured with **SYNC_JOB_INTERVAL_SECONDS**
    `"]
    B --> C["`
    Call backend **GET** /sync/ to get sync job parameters from the backend
    `"]
    C --> D[Get the current Sierra database time with its configured timezone]
    D --> E@{ shape: diamond, label: "Sync configuration is SYNC_FULL or SYNC_CHANGES?" }
    E -- SYNC_FULL --> F[Load Sierra items that have larger record_id than that passed in sync job parameters]
    E -- SYNC_CHANGES --> G[Load Sierra items that have have changed since the timestamp  passed in sync job parameters]
    F --> H[Convert the database query into Pandas dataframe and convert it to TSV]
    G --> H
    H --> I["`
    Gzip the TSV, and mutipart **POST** /sync/ with database timestamp as a data field`"]
    I --> B
```

## Environment Variables
- `ENV`
- `DB_HOST`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_PORT`
- `BACKEND_URL`
- `ETL_CLIENT_API_KEY`
- `MAX_SYNC_DELTA_MINUTES`
- `SYNC_JOB_INTERVAL_SECONDS`
- `SYNC_JOB_MISFIRE_GRACE_TIME_SECONDS`
- `LOG_LEVEL`
- `SENTRY_DSN`
- `SENTRY_RELEASE`

## License

MIT License

## Authors

- Mikko Vihonen