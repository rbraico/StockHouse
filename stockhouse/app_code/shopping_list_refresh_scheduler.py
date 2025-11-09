import sqlite3
import threading
import time
from datetime import datetime, timedelta
from config import Config


"""
Modulo per gestire uno scheduler giornaliero:
- Avvia un thread daemon all'avvio di StockHouse
- Calcola il tempo fino alle 00:01 del giorno successivo
- Esegue trigger_event() ogni giorno alle 00:01
"""

def trigger_event(key_name: str = "shopping_list_refresh_needed", value: str = "1"):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_state (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key_name, value))
    conn.commit()
    conn.close()
    print(f"[{datetime.now()}] Scrittura completata: {key_name} = {value}")

def start_daily_scheduler():
    def scheduler():
        try:
            while True:
                now = datetime.now()
                # Calcola domani alle 00:01
                next_run = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
                sleep_seconds = (next_run - now).total_seconds()
                print(f"[{now}] Dormo {sleep_seconds:.0f} secondi fino alle {next_run.time()} per il trigger giornaliero...")
                time.sleep(sleep_seconds)

                # Trigger iniziale
                trigger_event()

                # Poi loop giornaliero
                while True:
                    next_run += timedelta(days=1)
                    sleep_seconds = (next_run - datetime.now()).total_seconds()
                    print(f"[{datetime.now()}] Dormo {sleep_seconds:.0f} secondi fino alle {next_run.time()} per il trigger giornaliero...")
                    time.sleep(sleep_seconds)
                    trigger_event()

        except Exception as e:
            print(f"[{datetime.now()}] Errore nel thread scheduler: {e}")

    threading.Thread(target=scheduler, daemon=True).start()
    print(f"[{datetime.now()}] Thread scheduler giornaliero avviato.")
