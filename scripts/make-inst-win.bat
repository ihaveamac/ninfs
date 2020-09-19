for /f "delims=" %%V in ('py -3 -c "from ninfs import __version__; print(__version__)"') do set VERSION=%%V

mkdir dist

"C:\Program Files (x86)\NSIS\makensis.exe" /NOCD /DVERSION=%VERSION% wininstbuild\installer.nsi
