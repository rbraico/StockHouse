from flask import Flask
from stockhouse.app_code.models import init_db
import os

# ✅ Importa la funzione di ricalcolo
from stockhouse.app_code.models import recalculate_seasonal_priorities, debug_print  # <-- adatta il percorso se serve

def create_app():
    base_dir = os.path.dirname(__file__)

    app = Flask(
        __name__,
        static_folder=os.path.join(base_dir, 'static'),
        static_url_path='/static'
    )

    app.secret_key = "super-secret"

    from stockhouse.app_code.routes import main
    app.register_blueprint(main)

    # ✅ Inizializza il database
    init_db()

    # ✅ Ricalcolo iniziale delle priorità stagionali allo startup
    try:
        debug_print("Startup: eseguo ricalcolo iniziale delle priorità stagionali...")
        recalculate_seasonal_priorities()
        debug_print("Ricalcolo iniziale completato con successo.")
    except Exception as e:
        debug_print("Errore nel ricalcolo iniziale delle priorità stagionali:", e)

    print("=== ROUTES DISPONIBILI ===")
    print(app.url_map)

    return app
