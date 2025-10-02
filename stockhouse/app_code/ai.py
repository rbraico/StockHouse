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
from stockhouse.app_code.models import lookup_products_by_name, lookup_products_by_id,  upsert_transaction_fact, upsert_expense
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
        spesa_totale = data.get("spesa_totale", 0.0)
        debug_print("modulo ai - shopping_receipt - Dati ricevuti:", shop_name, data_scontrino, prodotti, spesa_totale)

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


        

        # Aggiorna expenses_fact se spesa_totale è presente
        if spesa_totale is not None and spesa_totale != 0:
            selected_decade = get_current_decade()
            conn = sqlite3.connect(Config.DATABASE_PATH)
            cursor = conn.cursor()
            upsert_expense(cursor, data_scontrino, selected_decade, shop_name, spesa_totale, mode="receipt")
            conn.commit()
            conn.close()

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
    
    model = genai.GenerativeModel('gemini-2.5-pro')
    
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
                con nome_negozio (se il negozio è Lidl, restituisci solo Lidl come nome), indirizzo_negozio,  \
                data_scontrino in formato yyyy-mm-dd, spesa_totale, lista_prodotti con nome_prodotto \
                ( non aggiungere nella lista prodotti le righe con prezzi negativi oppure i prodotti che iniziano con Statiegeld.\
                il nome_prodotto non deve contenere caratteri come %, ^, !, $ , oppure contengano parole come statiegeld), \
                quantita (arrotondata al valore intero piu` vicino), traduzione_italiano (traduzione sintetica in italiano), \
                prezzo_unitario e prezzo_totale (anche se coincidono). Se trovi prezzi negativi, sottrai dal prezzo del prodotto precedente; \
                Negli scontrini di Lidl, 'Volkoren ontbijt' e 'Brinta' sono due prodotti diversi. \
                Rispondi esclusivamente con il JSON."
    

    
    # Aggiunge la domanda all'inizio della lista di contenuti
    content_list.insert(0, question)
    
    try:
        response = model.generate_content(content_list)
        description = response.text
        debug_print("modulo ai - analyze_receipt_with_gemini - Response: OK", description)
        return description
    except Exception as e:
        debug_print(f"Errore durante la chiamata a Gemini: {e}")
        return None


def analyze_folder_products_with_gemini(filename, upload_folder):
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
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                img = PIL.Image.open(io.BytesIO(img_data))
                content_list.append(img)
            doc.close()
        except Exception as e:
            debug_print(f"Errore nella lettura del PDF: {e}")
            return None
    else:
        try:
            img = PIL.Image.open(file_path)
            content_list.append(img)
        except Exception as e:
            debug_print(f"Errore nella lettura dell'immagine: {e}")
            return None
    
    if not content_list:
        return None
    
    question = "Analizza il volantino incluso e restituisci esclusivamente in formato JSON i primi 10 prodotti alimentari presenti. \
                Per ciascun prodotto includi: nome_negozio, nome_prodotto, prezzo_originale, \
                prezzo_scontato, data_inizio_offerta (formato yyyy-mm-dd), data_fine_offerta (formato yyyy-mm-dd). \
                Se il volantino e` del negozio Lidl, le date di validita della offerta sono indicate nella parte alta della prima pagina. \
                applica queste date a tutti i prodotti. \
                Se non trovi queste date, imposta i campi data_inizio_offerta e data_fine_offerta su null. \
                Non aggiungere alcun commento, introduzione o spiegazione. Rispondi solo con il JSON."

    content_list.insert(0, question)
    
    try:
        response = model.generate_content(content_list)
        description = response.text
        debug_print("modulo ai - analyze_folder_products_with_gemini - Response: OK", description)
        return description
    except Exception as e:
        debug_print(f"Errore durante la chiamata a Gemini: {e}")
        return None





import imaplib
import email
import os

def download_vomar_emails():
    IMAP_SERVER = "imap.gmail.com"
    EMAIL_ACCOUNT = "rbraico.rb@gmail.com"
    PASSWORD = "nyhj enep wqlt tqgd"
    SAVE_FOLDER = r"//192.168.1.141/config/www" 

    # Crea la cartella se non esiste
    if not os.path.exists(SAVE_FOLDER):
        os.makedirs(SAVE_FOLDER)

    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL_ACCOUNT, PASSWORD)
    mail.select("inbox")

    status, data = mail.search(None, 'FROM "roberto.braico@live.com"')

    if status != "OK":
        print("❌ Errore nella ricerca.")
        return

    mail_ids = data[0].split()
    for i, mail_id in enumerate(mail_ids):
        status, msg_data = mail.fetch(mail_id, "(RFC822)")
        if status != "OK":
            print(f"⚠️ Errore nel recupero dell'email ID {mail_id}")
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Salva come file .eml
        filename = f"vomar_email_{i+1}.eml"
        filepath = os.path.join(SAVE_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(raw_email)

        print(f"📩 Email salvata: {filename}")

    mail.logout()





"""
def fetch_shopping_list():
    debug_print("Volantino LidlL..")

    # Esempio di utilizzo
    url_pdf = "https://object.storage.eu01.onstackit.cloud/leaflets/pdfs/0198e684-473b-72c7-bb4f-8a6f9e15372f/Folder-Week-36-01-09-07-09-06.pdf"
    nome_file = "volantino_lidl_settimana36.pdf"

    scarica_pdf(url_pdf, nome_file)
    return nome_file
"""

"""
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

    offerte = ordina_lista_spesa(json_output)
    #debug_print("Lista spesa ordinata:", offerte)
   
    print(f"\n🎯 Trovate {len(offerte)} offerte:\n")
    for offerta in offerte:
        print(json.dumps(offerta, indent=2, ensure_ascii=False))

    with open("offerte_lidl.json", "w", encoding="utf-8") as f:
        json.dump(offerte, f, indent=2, ensure_ascii=False)
"""