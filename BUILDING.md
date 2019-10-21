This is a work in progress. Send me a message if something about this doesn't work right.

Install [PyInstaller](https://pypi.org/project/PyInstaller/), [pycryptodomex](https://pypi.org/project/pycryptodomex/), and [PySide2](https://pypi.org/project/PySide2/) through pip. To build wheels, [wheel](https://pypi.org/project/wheel/) is required.

## macOS
Main build environment: 10.15 Supplemental Update; Python 3.6.8, 3.7.5, and 3.8.0 for macOS 10.9 from python.org

Python versions for 10.6 will not work because the C extension doesn't build with it.

### Building application
* `./scripts/make-app-mac.sh` - build `dist/ninfs.app` using 3.7
* `./scripts/make-dmg.sh` - build `dist/ninfs-$NV-macos.dmg` (e.g. `ninfs-2.0-macos.dmg`)
### Build for PyPI
* `./scripts/make-wheels.sh` - build wheels for 3.6, 3.7, and 3.8
* `python3 setup.py sdist` - build source distribution

## Windows
Main build environment: Windows 10, version 1903 x64, Python 3.6.8, 3.7.5, and 3.8.0 32-bit and 64-bit from python.org

These scripts assume both 32-bit and 64-bit versions of Python 3.6, 3.7, and 3.8 are installed.

### Building application
* `scripts\make-exe-win.bat` - build `dist\ninfs-win32.exe` and `dist\ninfs-win64.exe` using 3.7
* `scripts\make-zip-win.bat` - build `dist\ninfs-%VERSION%-win32.zip` and `dist\ninfs-%VERSION%-win64.zip` (e.g. `ninfs-2.0-win32.zip`)
### Build for PyPI
* `scripts\make-wheels.bat` - build wheels for 3.6, 3.7, and 3.8, 32-bit and 64-bit
