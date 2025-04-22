from flask import Flask
from stockhouse.app_code.models import init_db

def create_app():
    app = Flask(__name__)
    app.secret_key = "super-secret"
    
    from stockhouse.app_code.routes import main
    app.register_blueprint(main)

    init_db()

    return app
