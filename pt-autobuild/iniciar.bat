@echo off
rem Abre el panel de pt-autobuild. Usa el entorno virtual (.venv o venv) si existe.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py
) else if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" app.py
) else (
    where pythonw >nul 2>nul && (start "" pythonw app.py) || (python app.py & pause)
)
