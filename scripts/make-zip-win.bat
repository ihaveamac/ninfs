for /f "delims=" %%V in ('py -3 -c "from ninfs import __version__; print(__version__)"') do set VERSION=%%V

set OUTDIR=build\zipbuild\ninfs-%VERSION%

mkdir dist
rmdir /s /q build\zipbuild
mkdir build
mkdir build\zipbuild
mkdir %OUTDIR%

copy LICENSE.md %OUTDIR%
copy README.md %OUTDIR%

xcopy /s /e /i /y build\exe.win32-3.8 %OUTDIR%

py -m zipfile -c dist\ninfs-%VERSION%-win32.zip %OUTDIR%
