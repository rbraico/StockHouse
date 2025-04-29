import os
import yaml

def get_debug_mode():
    try:
        # Percorso del file config.yaml
        file_path = '/data/options.json' if os.name != 'nt' else 'config.yaml'

        # Leggi il file YAML
        with open(file_path, 'r') as f:
            config = yaml.safe_load(f)
            # Restituisci il valore di debug_mode
            return config.get('options', {}).get('debug_mode', False)
    except Exception as e:
        # Fallback a False se il file non esiste o c'è un errore
        print(f"[ERROR] Impossibile leggere debug_mode: {e}")
        return False
    
def debug_print(*args):
    if get_debug_mode():
        print(*args)