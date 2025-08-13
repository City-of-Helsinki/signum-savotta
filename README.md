# Signum-savotta

Signum-savotta is a desktop application for shelf mark printing with a REST API backend and ETL components providing Sierra LMS integration. The desktop application is designed for Windows and built with Python, PySide6 (Qt for Python), and QML. The backend and the ETL component are built with PostgreSQL, FastAPI and APScheduler.

The solution is designed to integrate with Brother QL label printers and 3M RFID readers with zero configuration to provide a seamless workflow for shelf mark printing without manual data entry. In addition, there is a lightweight API key management to ensure that only registered clients are able to make requests that would alter data in the solution's own and the database of Sierra LMS.

## Features

- **RFID Tag Reading:** Supports 3M RFID readers for tag detection.
- **Label Printing:** Integrates with Brother QL printers for high-quality label printing.
- **Modern UI:** Built with QML and PySide6
- **Status Monitoring:** Real-time feedback for reader, printer, battery, and overall system status.
- **Resource Management:** Uses Qt resource system (`.qrc`) for icons, fonts, and images.

## Requirements

- Python 3.10+
- Windows 10/11
- [PySide6](https://pypi.org/project/PySide6/)
- [brother_ql](https://pypi.org/project/brother_ql/)
- [Pillow](https://pypi.org/project/Pillow/)
- [pyserial](https://pypi.org/project/pyserial/)

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

3. Activate desktop application environment:
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
application/
├── main.qml           # Main QML UI
├── assets.qrc         # Qt resource file
├── src/
│   ├── main.py        # Python entry point
│   ├── assets_rc.py   # Compiled Qt resources
│   └── ...            # Other modules
```

## Notes

- Make sure your Brother QL printer and 3M series 210 RFID reader are connected before starting the application.
- For custom label sizes or printer models, update the configuration in the UI or source code.
- If you add new resources (images, fonts), update `assets.qrc` and recompile with `pyside6-rcc`.

## License

MIT License

## Authors

- Mikko Vihonen