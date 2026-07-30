@echo off
chcp 65001 >nul
title Leaseir - Extraccion diaria de Holded
cd /d "%~dp0"

if not exist holded.key (
  echo  Falta holded.key en esta carpeta. Ejecuta antes 1_PROBAR_HOLDED.bat
  pause & exit /b 1
)
set /p HOLDED_API_KEY=<holded.key

python -c "import requests" 2>nul || python -m pip install requests --quiet
python holded_extract.py --desde 2024-01-01
if errorlevel 1 (echo. & echo  LA EXTRACCION HA FALLADO & pause & exit /b 1)
echo.
echo  Listo. holded.json actualizado en _data_holded\
timeout /t 5 >nul
