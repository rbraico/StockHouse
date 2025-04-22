from flask import Flask, render_template, request, flash
from stockhouse.app_code.routes import main as main_blueprint  # Importa il blueprint 'main'
from stockhouse.app_code.models import init_db, save_product, get_all_products, get_all_shop_list, get_all_categories
from stockhouse.app_code.barcode import lookup_barcode
from config import Config

app = Flask(__name__)
app.config.from_object(Config)  # Carica la configurazione dalla classe Config

# ✅ Registriamo il blueprint
app.register_blueprint(main_blueprint, url_prefix='/')  # Usa url_prefix per associare il blueprint alla root

# Inizializza il database
init_db()

if __name__ == "__main__":
    app.run(debug=True)   
