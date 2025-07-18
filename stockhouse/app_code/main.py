from flask import Flask, render_template, request, flash
from stockhouse.app_code.routes import main as main_blueprint  # Importa il blueprint 'main'
from stockhouse.app_code.models import init_db
from stockhouse.app_code.barcode import lookup_barcode
from config import Config
import os

app = Flask(__name__)
app.config.from_object(Config)  # Carica la configurazione dalla classe Config

# ✅ Registriamo il blueprint
app.register_blueprint(main_blueprint, url_prefix='/')  # Usa url_prefix per associare il blueprint alla root

# Inizializza il database
init_db()

if __name__ == "__main__":
    debug_mode = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    app.run(debug=debug_mode)
