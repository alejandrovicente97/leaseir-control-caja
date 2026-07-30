@echo off
chcp 65001 >nul
title Leaseir - Probar conexion con Holded
cd /d "%~dp0"

if not exist holded.key (
  echo.
  echo  No encuentro el fichero holded.key
  echo  Crealo en esta misma carpeta con tu token de Holded dentro, en una sola linea.
  echo  Se saca en: Holded ^> Ajustes ^> Desarrolladores ^> Credenciales
  echo.
  pause & exit /b 1
)
set /p HOLDED_API_KEY=<holded.key

python -c "import requests" 2>nul || python -m pip install requests --quiet
python holded_extract.py --probar
echo.
pause
