pip install -r requirements.txt
pyside6-rcc assets.qrc -o src/assets_rc.py
pyinstaller --onefile --icon=assets\signumsavotta.ico --noconsole .\src\main.py