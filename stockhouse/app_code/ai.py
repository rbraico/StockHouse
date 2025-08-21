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
        debug_print("shopping_receipt - Dati ricevuti:", shop_name, data_scontrino, prodotti)

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
            product_id, confidence = fuzzy_match_product(nome_grezzo, aliases)
            

            if confidence < 0.90:
                note = f"Confidenza bassa: {round(confidence * 100)}%"
                insert_unknown_product(
                    shop_name=shop_name,
                    raw_name=nome_grezzo,
                    normalized_name=normalized,
                    matched_product_id=product_id,
                    note=note,
                    traduzione_italiano=traduzione_italiano,
                    quantita=quantita,
                    prezzo_unitario=prezzo_unitario,
                    prezzo_totale=prezzo_totale
                )
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



def analyze_receipt_with_gemini(filename, upload_folder):
    # Costruisci il path come Node-RED lo passa
    file_path = f"{upload_folder}/{filename}"  # o il path corretto che Node-RED usa

    genai.configure(api_key="AIzaSyBfqfUJVEvYZwlrkMXcO6s2H3PmiZhj-nY")

    img = PIL.Image.open(file_path) 

    model = genai.GenerativeModel('gemini-1.5-flash')

    question = "Analizza lo scontrino e restituisci solo il risultato in JSON senza testo introduttivo o commenti, \
                con nome_negozio (se il negozio è Lidl, restituisci solo Lidl come nome), indirizzo_negozio, \
                data_scontrino in formato yyyy-mm-dd (date in input che utilizzano / come separatori, sono da interpretarsi con il formato dd/mm/yyyy), spesa_totale, lista_prodotti con nome_prodotto \
                (non aggiungere prodotti con prezzi negativi o che iniziano con Statiegeld), \
                quantita (arrotondata), traduzione_italiano, prezzo_unitario e prezzo_totale.\
                Se trovi prezzi negativi, sottrai dal prezzo del prodotto precedente; rispondi esclusivamente con JSON."
    
    response = model.generate_content([question, img])
    description = response.text
    debug_print("modulo ai - analyze_receipt_with_gemini - Response: OK")

    return description


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




def offerte_lidle_openai():
    """
    Estrae 10 prodotti alimentari in offerta dal sito Reclamefolder.nl
    per Lidl Heerhugowaard usando GPT-4o full con browsing/web access.
    Restituisce il risultato in JSON.
    """

    debug_print("Recupero offerte Lidl con GPT-4o full...")

    prompt = """
    Da questo sito: Reclamefolder.nl, estrai 10 prodotti alimentari in offerta
    per Lidl Heerhugowaard. Restituisci SOLO JSON valido, senza testo aggiuntivo,
    spiegazioni o ragionamenti. Il JSON deve avere per ogni prodotto i campi:
    nome, prezzo, categoria (se possibile), link (se disponibile).

    Esempio di struttura JSON:
    [
      {"nome": "IJsbergsla", "prezzo": "€0,49", "categoria": "Frutta/verdura", "link": "https://..."},
      {"nome": "...", "prezzo": "...", "categoria": "...", "link": "..."},
      ...
    ]
    """

    try:
        # Imposta la chiave API
        openai.api_key = Config.OPENAI_API_KEY
        print("DEBUG API KEY:", Config.OPENAI_API_KEY[:28], "…")

        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-full",  # Modello potente con capacità browsing/web
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.1,
            # tools=["web-browsing"]  # se l'ambiente supporta strumenti, abilita browsing
        )

        debug_print("OpenAI response:") 
        print(response)  # stampa tutto l'oggetto
        print(response.choices[0].message.content)  # stampa il contenuto

        # Estrazione JSON
        content = response.choices[0].message.content.strip()
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

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json

import requests
import re
import json

def estrai_offerte_lidl(max_prodotti=10):
    print("Estrazione offerte Lidl da Reclamefolder.nl...")
    url = "https://www.reclamefolder.nl/aanbiedingen/?Winkel=Lidl"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html = response.text

        # Cerca pattern: prezzo seguito da nome prodotto
        pattern = r"€\s?\d+,\d{2}\s+([A-Z][^\n\r]+)"
        matches = re.findall(pattern, html)

        prodotti = []
        for match in matches:
            prezzo_match = re.search(rf"(€\s?\d+,\d{{2}})\s+{re.escape(match)}", html)
            if prezzo_match:
                prodotti.append({
                    "nome": match.strip(),
                    "prezzo": prezzo_match.group(1)
                })
            if len(prodotti) >= max_prodotti:
                break

        print(f"Offerte trovate: {len(prodotti)}")
        return json.dumps(prodotti, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"Errore durante l'estrazione: {e}")
        return json.dumps([], indent=2, ensure_ascii=False)




def estrai_offerte_with_gemini():
    # Costruisci il path come Node-RED lo passa


    genai.configure(api_key="AIzaSyBfqfUJVEvYZwlrkMXcO6s2H3PmiZhj-nY")



    model = genai.GenerativeModel('gemini-1.5-flash')

    question = """
            estrai dal sito https://www.lidl.nl/?utm_source=google&utm_medium=cpc&utm_campaign=&utm_content=145858794437&utm_term=lidl&cid=19643701620&gad_source=1&gad_campaignid=19643701620&gclid=Cj0KCQjwh5vFBhCyARIsAHBx2wwTpQ9s4I_ysTg1v7bcg94ejBKr0A6W9pz_-qnAzz6EZYkiWKRgNbUaAih4EALw_wcB i primi 3 prodotti alimentari in offerta (in olandese: aanbieding) della settimana corrente, con il nome del prodotto il prezzo originale e il prezzo in offerta e url del sito dove hai trovato i dati.
            Ignora contenuti non testuali o non leggibili. Restituisci solo un oggetto JSON con la seguente struttura:

            [
            {
                "nome_prodotto": "nome del prodotto",
                "prezzo_originale": "prezzo in euro",
                "prezzo_offerta": "prezzo in euro",
                "url": url del sito dove hai trovato i dati"
            },
            ...
            ]

            Rispondi esclusivamente con JSON, senza alcuna spiegazione o testo aggiuntivo.
            """
   
    response = model.generate_content([question])
    description = response.text
    debug_print("modulo ai - analyze_receipt_with_gemini - Response: OK")

    return description



    
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

    debug_print("Shopping list fetched:", json_output)


    # Chiudi la connessione
    conn.close()

    #prodotti_ordinati = ordina_prodotti_openai(json_output)
    offerte=estrai_offerte_with_gemini()
    debug_print("Shopping list fetched and ordered:", offerte)


