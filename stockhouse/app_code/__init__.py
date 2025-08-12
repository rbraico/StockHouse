from flask import Flask
from stockhouse.app_code.models import init_db
import os

def create_app():
    base_dir = os.path.dirname(__file__)  # cartella in cui si trova __init__.py

    app = Flask(
        __name__,
        static_folder=os.path.join(base_dir, 'static'),
        static_url_path='/static'
    )

    app.secret_key = "super-secret"

    from stockhouse.app_code.routes import main
    app.register_blueprint(main)

    init_db()

    print("=== ROUTES DISPONIBILI ===")
    print(app.url_map)

    return app



