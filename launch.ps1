# Lanzador de Cat_flip para Windows (PowerShell)
Set-Location $PSScriptRoot

# Activar entorno virtual
& ".venv\Scripts\Activate.ps1"

# Iniciar el servidor en segundo plano
$server = Start-Process python -ArgumentList "app.py" -PassThru -WindowStyle Hidden

# Esperar y abrir el navegador
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:5050"

Write-Host "Cat_flip corriendo en http://127.0.0.1:5050"
Write-Host "Presiona Ctrl+C para detener el servidor."

# Mantener el script activo hasta que el usuario lo cierre
try {
    Wait-Process -Id $server.Id
} finally {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
}
