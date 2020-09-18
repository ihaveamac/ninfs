for /f "delims=" %%V in ('py -3 -c "from ninfs import __version__; print(__version__)"') do set VERSION=%%V

set OUTDIR=build\zipbuild\ninfs-%VERSION%

mkdir dist
rmdir /s /q build\zipbuild
mkdir %OUTDIR% || exit /b

copy LICENSE.md %OUTDIR% || exit /b
copy README.md %OUTDIR% || exit /b

xcopy /s /e /i /y build\exe.win32-3.8 %OUTDIR% || exit /b

py -m zipfile -c dist\ninfs-%VERSION%-win32.zip %OUTDIR% || exit /b
