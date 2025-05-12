import os
import yaml

def get_debug_mode():
    try:
        # Percorso assoluto del file config.yaml
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Directory principale del progetto
        file_path = os.path.join(base_dir, 'config.yaml')

        # Debug: stampa il percorso del file
        #print(f"[DEBUG] Percorso del file YAML: {file_path}")

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