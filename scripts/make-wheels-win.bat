@echo off
REM Error checking from: https://stackoverflow.com/questions/734598

for %%A in (32,64) do (
    for %%V in (3.6,3.7,3.8) do (
        py -%%V-%%A setup.py bdist_wheel
        if %errorlevel% neq 0 exit /b %errorlevel%
    )
)
