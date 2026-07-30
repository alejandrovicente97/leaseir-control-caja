@echo off
chcp 65001 >nul
title Leaseir - Programar extraccion diaria
cd /d "%~dp0"
echo.
echo  Voy a crear una tarea de Windows que ejecuta la extraccion de Holded
echo  todos los dias laborables a las 07:30.
echo.
pause
schtasks /Create /TN "Leaseir - Extraer Holded" /TR "\"%~dp02_EXTRAER_HOLDED.bat\"" /SC WEEKLY /D LUN,MAR,MIE,JUE,VIE /ST 07:30 /F
if errorlevel 1 (
  echo.
  echo  No se ha podido crear. Prueba a abrir este .bat como administrador.
) else (
  echo.
  echo  Tarea creada. Se puede ver en el Programador de tareas de Windows.
)
echo.
pause
