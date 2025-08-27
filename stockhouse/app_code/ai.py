from stockhouse.utils import debug_print
import os
import google.generativeai as genai
import PIL.Image
import json
import re
import requests

import sqlite3
import openai
from config import Config

from stockhouse.utils import debug_print
from stockhouse.app_code.models import lookup_products_by_name, lookup_products_by_id,  upsert_transaction_fact
from stockhouse.app_code.shopping_list_utils import get_current_decade, normalize_text, fuzzy_match_product, lookup_products_by_name, get_aliases_from_db, insert_unknown_product


def manage_shopping_receipt(receipt_json):
    try:
        #debug_print("shopping_receipt - Dati ricevuti:", receipt_json)
        # Rimuovi eventuali delimitatori ```json ... ```
        clean_text = re.sub(r"^```json\n?|```$", "", receipt_json.strip())
        data = json.loads(clean_text)

        prodotti = data.get("lista_prodotti", [])
        shop_name = data.get("nome_negozio", "")
        data_scontrino = data.get("data_scontrino", None)
        debug_print("modulo ai - shopping_receipt - Dati ricevuti:", shop_name, data_scontrino, prodotti)

        # Seleziona la decade corrente
        decade_number = get_current_decade()

        # Carica alias
        aliases = get_aliases_from_db(shop_name) or get_aliases_from_db()

        results = []
        for prod in prodotti:
            # gestione prodotti come prima
            nome_grezzo = prod.get("nome_prodotto", "")
            traduzione_italiano = prod.get("traduzione_italiano", "")
            quantita = prod.get("quantita", None)
            prezzo_unitario = prod.get("prezzo_unitario", None)
            prezzo_totale = prod.get("prezzo_totale", None)

            if quantita == 1 and (prezzo_unitario is None or prezzo_unitario == 0):
                prezzo_unitario = prezzo_totale

            normalized = normalize_text(nome_grezzo)
            product_id, confidence, matched_name = fuzzy_match_product(nome_grezzo, aliases)


            if confidence < 0.95:
                note = f"Confidenza bassa: {round(confidence * 100)}%"


                insert_unknown_product(
                    shop_name=shop_name,
                    raw_name=nome_grezzo,
                    matched_product_id=product_id,
                    normalized_name=normalized,
                    note=note,
                    traduzione_italiano=traduzione_italiano,
                    quantita=quantita,
                    prezzo_unitario=prezzo_unitario,
                    prezzo_totale=prezzo_totale
                )
                debug_print(f"Prodotto non trovato o confidenza bassa, inserito in unknown_products: {nome_grezzo} ({note})")
            else:
                #prodotto_per_nome = lookup_products_by_name(nome_grezzo)
                prodotto_per_nome = lookup_products_by_id(product_id)

                if prodotto_per_nome["found"]:
                    product_key = prodotto_per_nome["id"]
                    barcode = prodotto_per_nome["barcode"]

                    upsert_transaction_fact(
                        product_key=product_key,
                        barcode=barcode,
                        price=prezzo_unitario,
                        quantity=quantita,
                        consumed_quantity=0,
                        ins_date=data_scontrino,
                        consume_date=None,
                        expiry_date=None,
                        status="in stock"
                    )
                else:
                    debug_print(f"Prodotto non trovato in product_dim: {nome_grezzo}")


        return ("Processed succesfully", 200)
    except Exception as e:
        debug_print("Errore in manage_shopping_receipt:", e)
        return ("Error during processing", 400)


# --- Funzione di analisi scontrino tramite Gemini AI ---


import fitz  # PyMuPDF
import PIL.Image
import io

def analyze_receipt_with_gemini(filename, upload_folder):
    # Costruisci il path
    file_path = f"{upload_folder}/{filename}"
    
    genai.configure(api_key="AIzaSyBfqfUJVEvYZwlrkMXcO6s2H3PmiZhj-nY")
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    content_list = []
    
    # Controlla l'estensione del file
    if filename.lower().endswith('.pdf'):
        try:
            doc = fitz.open(file_path)
            for page in doc:
                # Converte la pagina in un'immagine PIL
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                img = PIL.Image.open(io.BytesIO(img_data))
                content_list.append(img)
            doc.close()
        except Exception as e:
            debug_print(f"Errore nella lettura del PDF: {e}")
            return None
    else:
        # Se non è un PDF, tratta il file come un'immagine
        try:
            img = PIL.Image.open(file_path)
            content_list.append(img)
        except Exception as e:
            debug_print(f"Errore nella lettura dell'immagine: {e}")
            return None
    
    # Se non c'è contenuto, esci
    if not content_list:
        return None
    
    question = "Analizza lo scontrino e restituisci solo il risultato in JSON senza testo introduttivo o commenti, \
              con nome_negozio (se il negozio è Lidl, restituisci solo Lidl come nome), indirizzo_negozio, \
              data_scontrino in formato yyyy-mm-dd (date in input che utilizzano / come separatori, sono da interpretarsi con il formato dd/mm/yyyy), spesa_totale, lista_prodotti con nome_prodotto \
              (non aggiungere prodotti con prezzi negativi o che iniziano con Statiegeld), \
              quantita (arrotondata), traduzione_italiano, prezzo_unitario e prezzo_totale.\
              Se trovi prezzi negativi, sottrai dal prezzo del prodotto precedente; rispondi esclusivamente con JSON."
    
    # Aggiunge la domanda all'inizio della lista di contenuti
    content_list.insert(0, question)
    
    try:
        response = model.generate_content(content_list)
        description = response.text
        debug_print("modulo ai - analyze_receipt_with_gemini - Response: OK")
        return description
    except Exception as e:
        debug_print(f"Errore durante la chiamata a Gemini: {e}")
        return None
    



def ordina_prodotti_zai(prodotti_json, api_key):
    """
    Ordina prodotti con Z.AI (con debug errori)
    """
    if isinstance(prodotti_json, str):
        prodotti = json.loads(prodotti_json)
    else:
        prodotti = prodotti_json
    
    prompt = f"""
Il json incluso contiene una lista di prodotti. Ordina questi prodotti secondo la sequenza dei reparti che si incontrano camminando in un  supermercato olandese.
Restituisci SOLO JSON valido, senza testo aggiuntivo, spiegazioni, ragionamenti o altro.
{json.dumps(prodotti, ensure_ascii=False)}
"""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "GLM-4.5-Flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 5000
    }
    
    response = requests.post(
        "https://api.z.ai/api/paas/v4/chat/completions",
        headers=headers,
        json=payload
    )

    # 👇 stampiamo SEMPRE la risposta raw
    print("DEBUG STATUS:", response.status_code)
    print("DEBUG BODY:", response.text)

    if response.status_code != 200:
        # non solleviamo subito, ma mostriamo cosa manda il server
        raise Exception(f"Errore Z.AI: {response.status_code} - {response.text}")
    
    content = response.json()['choices'][0]['message']['content']
    return json.dumps(json.loads(content), indent=2, ensure_ascii=False)



from openai import OpenAI
def ordina_prodotti_openai(prodotti_json):
    """
    Ordina prodotti usando OpenAI (gpt-4o-mini)
    """

    debug_print("Ordina prodotti con OpenAI...")
    
    if isinstance(prodotti_json, str):
        prodotti = json.loads(prodotti_json)
    else:
        prodotti = prodotti_json

    prompt = f"""
    Hai una lista di prodotti in formato JSON. Ordina la lista simulando il percorso in un supermercato NL:
1. Frutta/verdura  
2. Pane e forno  
3. Snack/dolci/bevande  
4. Salumi/formaggi  
5. Latte, succhi, yogurt  
6. Surgelati  
7. Igiene/casa  
8. Cassa (caramelle, riviste).
 Restituisci SOLO JSON valido,senza testo aggiuntivo, spiegazioni o ragionamenti.

Per ogni prodotto, ricerca nei siti del negozio se esiste un prodotto simile in offerta. Se trovato, aggiungi nel JSON i campi "alternativa" con i dettagli del prodotto alternativo  :
nome; prezzo; negozio.

 Lista di prodotti da ordinare:
    {json.dumps(prodotti, ensure_ascii=False)}
    """


    try:
        # Imposto la chiave direttamente
        openai.api_key = Config.OPENAI_API_KEY
        print("DEBUG API KEY:", Config.OPENAI_API_KEY[:28], "…")  # non mostrare tutta la chiave

#        response = openai.chat.completions.create(
#            model="gpt-4o-mini",
#            messages=[{"role": "user", "content": prompt}],
#            temperature=0.1,
#            max_tokens=8000
#        )

        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8000,
            temperature=0.1
        )

        debug_print("OpenAI response:") 
        print(response)  # stampa tutto l'oggetto
        print(response.choices[0].message.content)  # stampa il contenuto

        # CORRETTO: accedi al contenuto così
        content = response.choices[0].message.content.strip()

        # fallback: estrai solo la parte JSON se l'AI ciancia
        match = re.search(r"\[.*\]", content, re.DOTALL)

        if match:
            content = match.group(0)
        else:
            raise ValueError(f"Nessun JSON valido nella risposta: {content[:200]}...")

        return json.dumps(json.loads(content), indent=2, ensure_ascii=False)


    except Exception as e:
        debug_print(f"[ERROR] Errore durante chiamata OpenAI: {e}")
        return json.dumps(prodotti, indent=2, ensure_ascii=False)



def cerca_offerte_lidl_openai():
    """
    Cerca offerte lidl usando OpenAI (gpt-4o-mini)
    """

    debug_print("cerca offerte lidl con OpenAI...")
   

    prompt = f"""
Cerca nel sito Lidl, localizzato per Heerhugowaard, le offerte settimanali disponibili a partire da lunedì nella sezione "Aanbiedingen vanaf maandag".
Estrai i primi 10 prodotti in offerta e restituiscili in formato JSON valido. Ogni oggetto deve contenere le seguenti chiavi:
product_name normal_price offer_price valid_from valid_to
I valori devono essere reali e corrispondere ai dati effettivi visibili sul sito. Non inventare nomi generici come "Product 1" o prezzi fittizi come "€X.XX". Non aggiungere testo, commenti o spiegazioni. Restituisci solo JSON puro.
    """


    try:
        # Imposto la chiave direttamente
        openai.api_key = Config.OPENAI_API_KEY
        print("DEBUG API KEY:", Config.OPENAI_API_KEY[:28], "…")

        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8000,
            temperature=0.1
        )

        debug_print("OpenAI response:") 
        print(response)  # stampa tutto l'oggetto
        print(response.choices[0].message.content)  # stampa il contenuto

        # CORRETTO: accedi al contenuto così
        content = response.choices[0].message.content.strip()

        # fallback: estrai solo la parte JSON se l'AI ciancia
        match = re.search(r"\[.*\]", content, re.DOTALL)

        if match:
            content = match.group(0)
        else:
            raise ValueError(f"Nessun JSON valido nella risposta: {content[:200]}...")

        return json.dumps(json.loads(content), indent=2, ensure_ascii=False)


    except Exception as e:
        debug_print(f"[ERROR] Errore durante chiamata OpenAI: {e}")
        return json.dumps([], indent=2, ensure_ascii=False)




import requests
from bs4 import BeautifulSoup
import json

def estrai_offerte_lidl():

    debug_print("Estrazione offerte Lidl...")
    
    url = "https://www.lidl.nl/c/aanbiedingen/a10008785?channel=store&tabCode=Current_Sales_Week"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    prodotti = []

    # Esempio semplificato: cerca blocchi di testo con prodotti
    # In un caso reale, dovresti analizzare la struttura HTML precisa
    offerte_raw = soup.get_text().split("Alleen in de winkel")
    for blocco in offerte_raw:
        if "met Lidl Plus" in blocco or "korting" in blocco:
            lines = blocco.strip().split("\n")
            nome = lines[0].strip() if lines else "Prodotto sconosciuto"
            prezzo_scontato = None
            prezzo_originale = None
            sconto = None

            for line in lines:
                if "met Lidl Plus" in line or "%" in line:
                    sconto = line.strip()
                elif "€" in line or line.replace(",", ".").replace("€", "").strip().replace(".", "").isdigit():
                    if not prezzo_originale:
                        prezzo_originale = line.strip()
                    else:
                        prezzo_scontato = line.strip()

            prodotti.append({
                "nome": nome,
                "prezzo_originale": prezzo_originale,
                "prezzo_scontato": prezzo_scontato,
                "sconto": sconto,
                "validità": "18/08 - 24/08",
                "solo_in_negizio": True
            })

    return json.dumps(prodotti, indent=2, ensure_ascii=False)




def estrai_offerte_with_gemini():

    genai.configure(api_key="AIzaSyBfqfUJVEvYZwlrkMXcO6s2H3PmiZhj-nY")

    model = genai.GenerativeModel('gemini-1.5-flash')

    question = "cerca nel sito https://www.reclamefolder.nl i prodotti in offerta per la settimana corrente. \
                Restituisci i dati reali trovati in formato JSON valido contenente le chiavi: nome_prodotto, contenente il nome del prodotto trovato, il prezzo_originale , contenente il prezzo prima dell'offerta,  e il prezzo_offerta, contenente il prezzo presente nell'offerta. \
                Supermercato, contenente il nome del supermercato o negozio che espone quella offerta; valida_da, contenente la data di inizio dell'offerta nel formato dd-mm-yyyy. Rispondi esclusivamente con JSON."
    
    response = model.generate_content([question])
    description = response.text
    debug_print("modulo ai - estrai_offerte_with_gemini - Response: OK")

    return description

import requests
import json
import re

def estrai_offerte_da_json(json_data):
    offerte = []

    for prodotto in json_data.get("products", []):
        titolo = prodotto.get("fullTitle", "Prodotto sconosciuto")
        badge = prodotto.get("stockAvailability", {}).get("badgeInfo", {}).get("badges", [])
        prezzo = prodotto.get("price", {}).get("price")
        prezzo_vecchio = prodotto.get("price", {}).get("oldPrice")

        # Cerca badge con "Alleen in de winkel"
        for b in badge:
            testo = b.get("text", "")
            if "Alleen in de winkel" in testo:
                validita = re.search(r"\d{2}/\d{2} - \d{2}/\d{2}", testo)
                offerte.append({
                    "nome_prodotto": titolo,
                    "prezzo_originale": prezzo_vecchio,
                    "prezzo_offerta": prezzo,
                    "valida_da": validita.group() if validita else None,
                    "supermercato": "Lidl"
                })

    return offerte

    url = "https://www.lidl.nl/api/v1/products?channel=store&tabCode=Current_Sales_Week"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    offerte = estrai_offerte_da_json(data)
    print(f"\n🎯 Trovate {len(offerte)} offerte:\n")
    for offerta in offerte:
        print(json.dumps(offerta, indent=2, ensure_ascii=False))

    with open("offerte_lidl.json", "w", encoding="utf-8") as f:
        json.dump(offerte, f, indent=2, ensure_ascii=False)



def fetch_shopping_list():
    debug_print("Fetching shopping list from database...")
    
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # Esegui la SELECT completa
    cursor.execute("select pd.item, sl.* from shopping_list sl join product_dim pd on sl.barcode=pd.barcode")
    rows = cursor.fetchall()

    # Recupera i nomi delle colonne
    columns = [description[0] for description in cursor.description]

    # Costruisci la lista di dizionari
    shopping_data = [dict(zip(columns, row)) for row in rows]

    # Converti in JSON e stampa
    json_output = json.dumps(shopping_data, indent=2, ensure_ascii=False)

    #debug_print("Shopping list fetched:", json_output)


    # Chiudi la connessione
    conn.close()

    url = "https://www.lidl.nl/api/v1/products?channel=store&tabCode=Current_Sales_Week"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    offerte = estrai_offerte_da_json(data)
    print(f"\n🎯 Trovate {len(offerte)} offerte:\n")
    for offerta in offerte:
        print(json.dumps(offerta, indent=2, ensure_ascii=False))

    with open("offerte_lidl.json", "w", encoding="utf-8") as f:
        json.dump(offerte, f, indent=2, ensure_ascii=False)
