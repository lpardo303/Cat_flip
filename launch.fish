#!/usr/bin/env fish
cd (dirname (status filename))
source .venv/bin/activate.fish
python app.py &
sleep 1
xdg-open http://127.0.0.1:5050
echo "✅ Cat_flip corriendo en http://127.0.0.1:5050"
wait
