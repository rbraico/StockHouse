import requests
import os
from config import Config

def lookup_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data.get("status") == 1:
            product = data["product"]
            #debug_print("lookup_barcode: ", product)

            # Preparo i dati principali
            name = product.get("product_name", "Unknown")
            brand = product.get("brands", "Unknown")
            image_url = product.get("image_url", None)
            
            # Cartella in cui salvare l'immagine
            image_folder = Config.get_image_folder()
            os.makedirs(image_folder, exist_ok=True)  # Creala se non esiste
            debug_print (f" 1-lookup_barcode[DEBUG] Image folder: {image_folder}")

            # Nome del file immagine
            image_filename = f"{barcode}.jpg"
            save_path = os.path.join(image_folder, image_filename)
            debug_print (f" 2-lookup_barcode[DEBUG] save_path: {save_path}")

            # Se c'è un'immagine, scaricala
            if image_url:
                try:
                    img_response = requests.get(image_url)
                    if img_response.status_code == 200:
                        with open(save_path, 'wb') as f:
                            f.write(img_response.content)
                        # Usare il path relativo per Home Assistant
                        relative_image_path = f"{image_folder}/{image_filename}"
                        debug_print (f" 3-lookup_barcode[DEBUG] relative_image_path: {relative_image_path}")
                    else:
                        relative_image_path = None  # Download fallito
                except Exception as e:
                    debug_print(f"Errore durante il download dell'immagine: {e}")
                    relative_image_path = None
            else:
                relative_image_path = None  # Nessuna immagine disponibile
            
            # Restituisci i dati del prodotto
            debug_print("lookup_barcode1: ", name, brand, relative_image_path)
            return {
                "name": name,
                "brand": brand,
                "quantity": 0,
                "image": relative_image_path  # Path locale o None
            }
        else:
            return {"error": "Prodotto non trovato"}
    else:
        return {"error": "Errore API"}