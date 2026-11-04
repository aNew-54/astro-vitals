@echo off
chcp 65001 >nul
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero instala el entorno siguiendo prototype\README.md.
    pause
    popd
    exit /b 1
)
".venv\Scripts\python.exe" "prototype\run.py"
if errorlevel 1 pause
popd
