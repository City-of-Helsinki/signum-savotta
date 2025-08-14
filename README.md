# Signum-savotta

Signum-savotta is a desktop application for shelf mark printing with a REST API backend and ETL components providing Sierra LMS integration. The desktop application is designed for Windows and built with Python, PySide6 (Qt for Python), and QML. The backend and the ETL component are built with PostgreSQL, FastAPI and APScheduler.

The solution is designed to integrate with Brother QL label printers and 3M RFID readers with zero configuration to provide a seamless workflow for shelf mark printing without manual data entry. In addition, there is a lightweight API key management to ensure that only registered clients are able to make requests that would alter data in the solution's own and the database of Sierra LMS.

> **Note**: This application evolved from a POC literally done overnight. Although manually tested it's missing test automation and CI/CD. City of Helsinki cannot provide support and the solution is published here for reference to whoever might find it interesting.

## Installation

1. Clone the repository:
   ```sh
   git clone https://github.com/City-of-Helsinki/signum-savotta.git
   cd signum-savotta
   ```

2. Start the backend / ETL infrastructure (needs Sierra API key + SierraDNA access):
   ```sh
   docker compose build
   docker compose up
   ```

3. Activate desktop application virtual environment:
   ```sh
   cd application
   ../activate_project.sh
   ```

4. Compile Qt resources:
   ```sh
   pyside6-rcc application/assets.qrc -o application/src/assets_rc.py
   ```

## Usage

Run the application:
```sh
cd application
python src/main.py
```

## Project Structure

```
application/           # The Desktop application
backend/               # The Backend supporting the desktop application
etl_component/         # ETL component responsible for synchronizing Sierra LMS item and bibliographic data to backend database
```

## License

MIT License

## Authors

- Mikko Vihonen (mikko.vihonen@nitor.com)