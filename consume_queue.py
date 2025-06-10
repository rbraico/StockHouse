import json
import time
import os

QUEUE_FILE = r"C:\Users\Gebruiker\Projects\shared_queue\shopping_queue.txt"

def consume_queue():
    while True:
        if not os.path.exists(QUEUE_FILE):
            time.sleep(2)
            continue
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if not lines:
            time.sleep(2)
            continue
        # Prendi il primo evento (FIFO)
        event = json.loads(lines[0])
        print("[STOCKHOUSE] Evento ricevuto:", event)
        # Riscrivi il file senza la prima riga
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines[1:])
        time.sleep(1)

if __name__ == "__main__":
    consume_queue()