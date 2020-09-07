This is still being worked on (as of September 6, 2020). Soon this will build a Windows installer, hopefully.

Python versions 3.6, 3.7, and 3.8 are required. For Windows, 32-bit and 64-bit versions are needed. For macOS, the 10.9 variant is required.

# Windows
Main build environment: Windows 10, version 1903 x64, Python 3.6.8, 3.7.9, and 3.8.5 32-bit and 64-bit from python.org

## Standalone build with cx\_Freeze
**This part is going to change a lot! I recognize that this part is a bit of a mess. This is temporary (as of September 6, 2020) for test releases.**

Install the dependencies:
```batch
py -3.8-32 -m pip install --user pycryptodomex==3.9.8 pyctr==0.4.3 cx-Freeze==6.2 wheel
```

Run the build script: `scripts\make-exe-win.bat`
This will build the exe and package it into a zip.

## Wheel build
`scripts\make-wheels-win.bat` - build wheels for 3.6, 3.7, and 3.8, 32-bit and 64-bit

# macOS
Main build environment: 10.15.6 Supplemental Update; Python 3.6.8, 3.7.9, and 3.8.5 for macOS 10.9 from python.org

No standalone build yet.

## Wheel build
`./scripts/make-wheels.sh` - build wheels for 3.6, 3.7, and 3.8
`python3 setup.py sdist` - build source distribution
