# Application

This is the desktop application for Signum-savotta, providing a modern UI for RFID tag reading and label printing.

## Features

- **RFID Tag Reading:** Supports 3M RFID readers for tag detection and registration.
- **Label Printing:** Integrates with Brother QL printers for shelf mark and custom label printing.
- **Modern UI:** Responsive interface built with QML and PySide6.
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

1. Create a Python virtual environment with dedicated script:
   ```sh
   cd application
   ../activate_project.sh
   ```

2. Compile Qt resources:
   ```sh
   pyside6-rcc assets.qrc -o src/assets_rc.py
   ```

## Usage

Run the application:
```sh
python src/main.py
```

## Packaging

To build a standalone executable with PyInstaller:
```sh
pyinstaller --onefile --icon=assets\signumsavotta.ico --noconsole .\src\main.py
```

## Project Structure

```
application/
├── main.qml           # Main QML UI
├── assets.qrc         # Qt resource file
├── assets/            # Icons, fonts, images
├── src/
│   ├── main.py        # Python entry point
│   ├── assets_rc.py   # Compiled Qt resources
│   └── ...            # Other modules
```

## Notes

- Ensure your Brother QL printer and 3M RFID reader are connected before starting the application.
- If you add new resources (images, fonts), update `assets.qrc` and recompile with `pyside6-rcc`.
- For custom label sizes or printer models, update the configuration in the UI or source code.

## License

MIT License

## Authors

- Mikko Vihonen (mikko.vihonen@nitor.com)