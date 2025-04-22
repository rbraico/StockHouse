import requests

def lookup_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data.get("status") == 1:
            product = data["product"]
            #print("Risultato:", product)  # 👈 Aggiungilo per vedere cosa arriva 
            return {
                "name": product.get("product_name", "Unknown"),
                "brand": product.get("brands", "Unknown"),
                "quantity": 0,
                "image": product.get("image_url", None)
            }
        else:
            return {"error": "Prodotto non trovato"}
    else:
        return {"error": "Errore API"}
