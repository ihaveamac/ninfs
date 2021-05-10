This is still being worked on (as of October 25, 2020).

# Windows

## Standalone build
This expects Python 3.8 32-bit to be installed.

Install the dependencies:
```batch
py -3.8-32 -m pip install --user cx-Freeze==6.6 -r requirements.txt
```

Build the exe:
```batch
scripts\make-exe-win.bat
```

Build the standalone zip:
```batch
scripts\make-zip-win.bat
```

Build the NSIS installer (by default this depends on it being installed to `C:\Program Files (x86)\NSIS`):
```
scripts\make-inst-win.bat
```

## Wheel and source dist build
* `py -3 setup.py bdist_wheel` - build multi-platform py3 wheel
* `py -3 setup.py sdist` - build source distribution

# macOS
This needs Python built with universal2 to produce a build with a working GUI. Despite that it currently doesn't produce a universal build (https://github.com/pyinstaller/pyinstaller/issues/5315).

Set up a venv, activate it, and install the requirements:
```sh
python3.9 -m venv venv39
source venv39/bin/activate
pip install pyinstaller certifi -r requirements.txt
```

Build the icns:
```sh
./scripts/make-icons.sh
```

Build the app:
```sh
pyinstaller standalone.spec
```

Build the dmg:
```sh
./scripts/make-dmg-mac.sh
```

todo:
* Use pyinstaller for Windows in the same spec file (trying to do this with nsis might suck)

## Wheel and source dist build
* `python3 setup.py bdist_wheel` - build multi-platform py3 wheel
* `python3 setup.py sdist` - build source distribution
