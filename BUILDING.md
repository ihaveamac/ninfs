This is still being worked on (as of September 18, 2020).

# Windows

## Standalone build
This expects Python 3.8 32-bit to be installed.

Install the dependencies:
```batch
py -3.8-32 -m pip install --user pycryptodomex==3.9.8 pyctr==0.4.3 cx-Freeze==6.2
```

Build the exe:
```batch
scripts\make-exe-win.bat
```

Build the standalone zip:
```batch
scripts\make-zip-win.bat
```

## Wheel and source dist build
`py -3 setup.py bdist_wheel` - build multi-platform py3 wheel
`py -3 setup.py sdist` - build source distribution

# macOS
No standalone build yet.

## Wheel and source dist build
`python3 setup.py bdist_wheel` - build multi-platform py3 wheel
`python3 setup.py sdist` - build source distribution
