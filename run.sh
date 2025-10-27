#!/bin/bash
# Avvia la tua applicazione Flask

echo "Avvio stockhouse Flask app..."
export FLASK_APP=stockhouse.app_code:create_app
export FLASK_RUN_HOST=0.0.0.0
export FLASK_RUN_PORT=9192

pip install -r /stockhouse/requirements.txt
flask run --host=0.0.0.0 --port=9192
