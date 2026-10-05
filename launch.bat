@echo off
:: Lanzador de Cat_flip para Windows
cd /d "%~dp0"

:: Activar entorno virtual
call .venv\Scripts\activate.bat 2>nul

:: Iniciar el servidor en segundo plano
start "" /B python app.py

:: Esperar un segundo y abrir el navegador
timeout /t 2 /nobreak >nul
start http://127.0.0.1:5050

echo Cat_flip corriendo en http://127.0.0.1:5050
echo Cierra esta ventana para detener el servidor.
pause
