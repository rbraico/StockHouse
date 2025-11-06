import os
import json
import secrets
import platform
from stockhouse.utils import debug_print

class Config:
    SECRET_KEY = secrets.token_hex(16)

    @staticmethod
    def get_database_path():
        db_path = os.getenv("DB_PATH")
        debug_print(f"[DEBUG] os.name = {os.name}")
        debug_print(f"[DEBUG] DB_PATH env = {db_path}")

        if db_path:
            dir_path = os.path.dirname(db_path)
            if not os.path.exists(dir_path):
                debug_print(f"[INFO] Directory {dir_path} non trovata, la creo...")
                os.makedirs(dir_path, exist_ok=True)

            if not os.path.exists(db_path):
                debug_print(f"[WARNING] DB file non trovato in {db_path}. Verrà creato da SQLite se necessario.")
            else:
                debug_print(f"[Config] DB trovato in: {db_path}")
            return db_path

        elif os.name == "nt":  # Windows
            path = os.path.join(os.getcwd(), "sqlite_db", "stockhouse.db")
            if not os.path.exists(os.path.dirname(path)):
                debug_print(f"[INFO] Creo cartella per DB locale: {os.path.dirname(path)}")
                os.makedirs(os.path.dirname(path), exist_ok=True)
            debug_print(f"[Config] Using Windows dev path: {path}")
            return path

        else:  # Linux/macOS/Home Assistant
            debug_print("[Config] Using default Linux/macOS path: ./stockhouse.db")
            return "./stockhouse.db"

    @staticmethod
    def get_image_folder():
        if platform.system() == "Windows":
            return r"\\192.168.1.31\Progetti\StockHouse\stockhouse_images"
        else:
            return "/config/www/stockhouse_images"

    @staticmethod
    def get_image_url():
        try:
            with open("/data/options.json") as f:
                config = json.load(f)
                base_url = config.get("base_url")
                if base_url:
                    return f"{base_url}/local/stockhouse_images"
        except Exception as e:
            debug_print(f"[ERROR] Impossibile leggere base_url da options.json: {e}")

        if platform.system() == "Windows":
            return "http://localhost:5000/images"

        return "http://localhost:8123/local/stockhouse_images"
    

       # 🧾 Nuova funzione per gli scontrini
    @staticmethod
    def get_receipt_folder():
        """
        Ritorna il percorso dove salvare gli scontrini.
        In Home Assistant: /config/www/uploaded_receipts
        In Windows: ./uploaded_receipts
        """
        if platform.system() == "Windows":
            path = os.path.join(os.getcwd(), "uploaded_receipts")
        else:
            path = "/config/www/uploaded_receipts"

        os.makedirs(path, exist_ok=True)
        debug_print(f"[Config] Receipt folder: {path}")
        return path

    # Inizializzazione statica
    DATABASE_PATH = get_database_path.__func__()
