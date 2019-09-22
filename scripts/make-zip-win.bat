@echo off
REM Error checking from: https://stackoverflow.com/questions/734598
REM Variable setting from: https://stackoverflow.com/questions/16203629

for /f "delims=" %%V in ('py -3 -c "from ninfs import __version__; print(__version__)"') do set VERSION=%%V

for %%A in (32,64) do (
    mkdir build\zip-win%%A
    copy dist\ninfs-win%%A.exe build\zip-win%%A\ninfs.exe
    if %errorlevel% neq 0 exit /b %errorlevel%

    REM more files will go here eventually

    py -3 -m zipfile -c dist\ninfs-%VERSION%-win%%A.zip build\zip-win%%A\ninfs.exe
    if %errorlevel% neq 0 exit /b %errorlevel%
)
