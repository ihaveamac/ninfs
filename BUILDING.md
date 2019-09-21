This is a work in progress. Send me a message if something about this doesn't work right.

Python versions for 10.6 will not work because the C extension doesn't build with it.

Install pyinstaller, pycryptodomex, and pyside2 through pip.

## macOS
Main build environment: 10.14.6 Supplemental Update 2, Python 3.6.8 and 3.7.4 for macOS 10.9 from python.org
### Building application
* `./scripts/make-app-mac.sh` - build `dist/ninfs.app`
* `./scripts/make-dmg.sh` - build `dist/ninfs-$NV.dmg` (e.g. `ninfs-2.0.dmg`)
### Build for PyPI
* `./scripts/make-wheels.sh` - build wheels for 3.6 and 3.7
* `python3 setup.py sdist` - build source distribution
