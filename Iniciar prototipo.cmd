@echo off
chcp 65001 >nul
pushd "%~dp0"
if not exist "prototype\.venv\Scripts\python.exe" (
    echo No se encontro prototype\.venv\Scripts\python.exe.
    echo Revisa prototype\README.md para instalar el entorno.
    pause
    popd
    exit /b 1
)
"prototype\.venv\Scripts\python.exe" "prototype\run.py" --web
if errorlevel 1 pause
popd
