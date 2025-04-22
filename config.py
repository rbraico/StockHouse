import os
import secrets

class Config:
    SECRET_KEY = secrets.token_hex(16)

    @staticmethod
    def get_database_path():
        db_path = os.getenv("DB_PATH")
        print(f"[DEBUG] os.name = {os.name}")
        print(f"[DEBUG] DB_PATH env = {db_path}")

        if db_path:
            dir_path = os.path.dirname(db_path)
            if not os.path.exists(dir_path):
                print(f"[INFO] Directory {dir_path} non trovata, la creo...")
                os.makedirs(dir_path, exist_ok=True)

            if not os.path.exists(db_path):
                print(f"[WARNING] DB file non trovato in {db_path}. Verrà creato da SQLite se necessario.")
            else:
                print(f"[Config] DB trovato in: {db_path}")
            return db_path

        # fallback per Windows (dev locale)
        elif os.name == "nt":
            path = os.path.join(os.getcwd(), "sqlite_db", "stockhouse.db")
            if not os.path.exists(os.path.dirname(path)):
                print(f"[INFO] Creo cartella per DB locale: {os.path.dirname(path)}")
                os.makedirs(os.path.dirname(path), exist_ok=True)
            print(f"[Config] Using Windows dev path: {path}")
            return path

        # fallback generico Linux/macOS
        else:
            print("[Config] Using default Linux/macOS path: ./stockhouse.db")
            return "./stockhouse.db"

    # Inizializzazione statica
    DATABASE_PATH = get_database_path.__func__()