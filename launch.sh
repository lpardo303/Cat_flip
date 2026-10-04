#!/bin/bash
# Lanzador de Cat_flip
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true
python app.py &
sleep 1
xdg-open http://127.0.0.1:5050
echo "✅ Cat_flip corriendo en http://127.0.0.1:5050 (cierra esta ventana para detenerlo)"
wait
