@echo off
chcp 65001 >nul
title Leaseir - Traer el dashboard de GitHub a OneDrive
cd /d "%~dp0"

set DESTINO=%USERPROFILE%\OneDrive - Leaseir Technologies\Leaseir - Finance - Documentos\General\Leaseir - Finance\2026\19. Control Caja\_motor_caja

echo  Bajando el ultimo dashboard del repositorio...
git pull --quiet
if errorlevel 1 (echo. & echo  No se ha podido hacer git pull. & pause & exit /b 1)

if not exist "publicado\index.html" (
  echo  Todavia no hay dashboard publicado. Lanza el workflow en GitHub ^> Actions.
  pause & exit /b 1
)

if not exist "%DESTINO%" mkdir "%DESTINO%"
copy /Y "publicado\index.html" "%DESTINO%\caja_leaseir.html" >nul
echo.
echo  Listo: %DESTINO%\caja_leaseir.html
start "" "%DESTINO%\caja_leaseir.html"
timeout /t 4 >nul
