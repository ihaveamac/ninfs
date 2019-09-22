This is a work in progress. Send me a message if something about this doesn't work right.

Install pyinstaller, pycryptodomex, and pyside2 through pip.

## macOS
Main build environment: 10.14.6 Supplemental Update 2, Python 3.6.8 and 3.7.4 for macOS 10.9 from python.org

Python versions for 10.6 will not work because the C extension doesn't build with it.

### Building application
* `./scripts/make-app-mac.sh` - build `dist/ninfs.app`
* `./scripts/make-dmg.sh` - build `dist/ninfs-$NV-macos.dmg` (e.g. `ninfs-2.0-macos.dmg`)
### Build for PyPI
* `./scripts/make-wheels.sh` - build wheels for 3.6 and 3.7
* `python3 setup.py sdist` - build source distribution

## Windows
Main build environment: Windows 7 x64, Python 3.6.8 and 3.7.4 32-bit and 64-bit from python.org

These scripts assume both 32-bit and 64-bit versions of Python 3.6 and 3.7 are installed.

### Building application
* `scripts\make-exe-win.bat` - build `dist\ninfs-win32.exe` and `dist\ninfs-win64.exe`
* `scripts\make-zip-win.bat` - build `dist\ninfs-%VERSION%-win32.zip` and `dist\ninfs-%VERSION%-win64.zip` (e.g. `ninfs-2.0-win32.zip`)
