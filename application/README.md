# Application

This is the desktop application for Signum-savotta, providing a modern UI for RFID tag reading and label printing.

## Features

- **RFID Tag Reading:** Supports 3M RFID readers for tag detection and registration.
- **Label Printing:** Integrates with Brother QL printers for shelf mark and custom label printing.
- **Modern UI:** Responsive interface built with QML and PySide6.
- **Status Monitoring:** Real-time feedback for reader, printer, battery, and overall system status.
- **Resource Management:** Uses Qt resource system (`.qrc`) for icons, fonts, and images.

> **Note**: The real time updates to the QML UI can cause flickering in the UI should there be rapid chages in the network connectivity, reader results etc.

## Requirements

- Python 3.14+
- Windows 10/11
- [brother_ql2](https://pypi.org/project/brother_ql2/)
- [Pillow](https://pypi.org/project/Pillow/)
- [PySide6](https://pypi.org/project/PySide6/)
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

## Configuration

The application configuration is stored in `config.ini` file located in the working directory.

## Usage

Run the application:
```sh
python src/main.py
```

## Building the Windows installer

The end-user deliverable is a single `SignumSavottaSetup.exe` produced by
`build.ps1`. Run it from the `application` directory in PowerShell:

```powershell
.\build.ps1
# or, if Inno Setup is installed somewhere unusual:
.\build.ps1 -InnoSetupPath "D:\Tools\InnoSetup6\ISCC.exe"
```

Output: `application\dist\SignumSavottaSetup.exe`.

### Prerequisites

- **Poetry** — used to run `pyside6-rcc` and `pyinstaller` inside the project
  virtualenv. Install dependencies once with `poetry install`.
- **Inno Setup 6** ([jrsoftware.org/issetup.php](https://jrsoftware.org/issetup.php)) —
  `build.ps1` auto-detects `ISCC.exe` in the standard install locations; pass
  `-InnoSetupPath` if it lives elsewhere.

### What the build does

`build.ps1` runs three steps:

1. **Compile Qt resources** — `pyside6-rcc assets.qrc -o src/assets_rc.py`.
2. **Bundle the app with PyInstaller** — `pyinstaller main.spec --clean --noconfirm`.
   The spec produces a windowed (no console) `main.exe` plus an `_internal`
   directory with the Python runtime and dependencies under `dist\main\`.
3. **Compile the installer** — `ISCC.exe installer.iss` packages
   `dist\main\`, the `assets\` folder, and `config.ini.example` (renamed to
   `config.ini` at install time) into `dist\SignumSavottaSetup.exe`.

### What the installer does

`installer.iss` is more than a file-copy script — read it before bumping the
version. Highlights:

- **Install location:** `C:\tulostus` (fixed, dir page disabled). Requires
  admin privileges for USB device access.
- **AppId:** `{6D4A2B1C-3E5F-4A8B-9C7D-E0F1A2B3C4D5}` — do **not** change
  after release, or Windows will treat upgrades as a separate application.
- **Version:** bump `MyAppVersion` in `installer.iss` for each release.
- **Config migration:** before overwriting `C:\tulostus`, the installer
  copies the existing `config.ini` to `%TEMP%`. After writing the new
  template, a PowerShell script merges the old `[registration]` (and any
  other previously-set values) into the new file and saves it as UTF-8
  without BOM — the encoding Python's `configparser` expects.
- **Runtime write access:** `icacls` grants `Users:(OI)(CI)M` on the install
  directory so the app can update `config.ini` at runtime without elevation.

### Iterating without rebuilding the installer

To test the bundled app without re-running Inno Setup, run only steps 1–2 and
launch `dist\main\main.exe` directly.

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