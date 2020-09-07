for /f "delims=" %%V in ('py -3 -c "from ninfs import __version__; print(__version__)"') do set VERSION=%%V

del ninfs\hac\*.pyd
del ninfs\hac\*.so

del build\ninfs-%VERSION%

py -3.8-32 setup-cxfreeze.py build_ext --inplace
py -3.8-32 setup-cxfreeze.py build_exe

del build\exe.win32-3.8\lib\ninfs\hac\*.cpp
del build\exe.win32-3.8\lib\ninfs\hac\*.pyi
del build\exe.win32-3.8\lib\ninfs\hac\*.h
del build\exe.win32-3.8\lib\ninfs\hac\*.dylib

mkdir dist
move build\exe.win32-3.8 build\ninfs-%VERSION%
copy LICENSE.md build\ninfs-%VERSION%
copy README.md build\ninfs-%VERSION%
py -m zipfile -c dist\ninfs-%VERSION%-win32.zip build\ninfs-%VERSION%
