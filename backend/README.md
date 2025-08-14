# Backend

The backend component provides REST API endpoints and manages the database for the Tarroitusratkaisu solution. It handles client registration, item data management, synchronization with Sierra LMS, and system state monitoring.

## Features

- **REST API:** FastAPI-based endpoints for item management, client registration, and system status.
- **Database Integration:** Uses SQLAlchemy for PostgreSQL database operations.
- **Periodic Synchronization:** Coordinates with the ETL component to keep item data up-to-date.
- **Client Management:** Supports API key registration and access control.
- **Error Reporting:** Integrated with Sentry for error tracking and diagnostics.
- **Configurable:** All connection and sync parameters are set via environment variables.

## Requirements

- Python 3.10+
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [httpx](https://www.python-httpx.org/)
- [sentry-sdk](https://pypi.org/project/sentry-sdk/)
- [Uvicorn](https://www.uvicorn.org/)

## Usage

Intended to be run using docker-compose locally (see root README.MD for reference) or deployed to a server.

## API Endpoints

- `/items/` – Manage item records
- `/clients/` – Register and manage API clients
- `/status/` – System and sync status
- `/sync/` – Trigger or monitor synchronization jobs
- `/docs/` - Swagger
- `/redoc/` - Redoc

## Environment Variables

- `ENV`
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `FULL_SYNC_BATCH_SIZE`
- `SIERRA_API_ENDPOINT`
- `SIERRA_API_CLIENT_KEY`
- `SIERRA_API_CLIENT_SECRET`
- `SIERRA_API_CLIENT_POOL_SIZE`
- `SIERRA_API_CLIENT_TIMEOUT_SECONDS`
- `SIERRA_API_CLIENT_RETRIES`
- `SIERRA_UPDATE_INTERVAL_SECONDS`
- `SIERRA_UPDATE_MISFIRE_GRACE_TIME_SECONDS`
- `SIERRA_UPDATE_BATCH_SIZE_LIMIT`
- `SIERRA_UPDATE_SET_INVDA`
- `SIERRA_UPDATE_SET_IUSE3`
- `LOG_LEVEL`
- `SENTRY_DSN`
- `SENTRY_RELEASE`

## License

MIT License

## Authors

- Mikko Vihonen

