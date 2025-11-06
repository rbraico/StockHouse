from stockhouse.utils import debug_print
import os
import google.generativeai as genai
import PIL.Image
import json
import re
import requests

import sqlite3
from config import Config

import openai
from openai import OpenAI
import fitz  # PyMuPDF
from PIL import Image
import io
import pytesseract
import json
import base64


# Percorso completo dell'eseguibile tesseract
#pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# Imposta la variabile TESSDATA_PREFIX alla cartella tessdata
#os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"
#print(pytesseract.get_tesseract_version())

if os.name == "nt":  # Windows
    # Percorsi per installazione locale
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"
else:
    # Percorsi per Home Assistant / Linux
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
    os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/5/tessdata/"

# (Facoltativo: stampa diagnostica)
# from stockhouse.utils import debug_print
debug_print(f"[AI] Tesseract path: {pytesseract.pytesseract.tesseract_cmd}")
debug_print(f"[AI] Tessdata prefix: {os.environ.get('TESSDATA_PREFIX')}")




from stockhouse.utils import debug_print
from stockhouse.app_code.models import lookup_products_by_name, lookup_products_by_id,  upsert_transaction_fact, upsert_expense
from stockhouse.app_code.shopping_list_utils import get_current_decade, normalize_text, fuzzy_match_product, lookup_products_by_name, get_aliases_from_db, insert_unknown_product
from dotenv import load_dotenv

# Carica il file .env dalla root del progetto
load_dotenv()


def manage_shopping_receipt(receipt_json):
    try:
        # Se è già un dict, salta parsing
        if isinstance(receipt_json, dict):
            data = receipt_json
        else:
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
    
    openai.api_key = os.getenv("gemini_api_key")  # o inserisci la tua chiave qui direttamente
    
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
    
    openai.api_key = os.getenv("gemini_api_key")  # o inserisci la tua chiave qui direttamente
    
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

#---------CHAT_GPT---------
def analyze_receipt_with_chatgpt(filename, upload_folder):
    # Costruisci il path completo
    file_path = f"{upload_folder}/{filename}"

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    content_list = []

    # Controlla l'estensione del file (PDF o immagine)
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

    # Prompt per ChatGPT
    question = (
        "Analizza lo scontrino e restituisci solo il risultato in formato JSON, senza testo introduttivo o commenti. "
        "Includi i seguenti campi: nome_negozio (se il negozio è Lidl, restituisci solo 'Lidl' come nome), "
        "indirizzo_negozio, data_scontrino (formato yyyy-mm-dd), spesa_totale, "
        "lista_prodotti con: nome_prodotto (escludi righe con prezzi negativi o nomi che iniziano con 'Statiegeld' "
        "o che contengono caratteri come %, ^, !, $, o la parola 'statiegeld'), "
        "quantita (arrotondata al valore intero più vicino), traduzione_italiano (sintetica), "
        "prezzo_unitario e prezzo_totale (anche se coincidono). "
        "Se trovi prezzi negativi, sottrai il valore dal prezzo del prodotto precedente. "
        "Negli scontrini di Lidl, 'Volkoren ontbijt' e 'Brinta' sono prodotti diversi. "
        "Rispondi esclusivamente con il JSON."
    )

    # Prepara i contenuti per il messaggio da mandare a GPT-4o
    message_content = [{"type": "text", "text": question}]
    for img in content_list:
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        image_b64 = base64.b64encode(buffer.read()).decode()
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"}
        })

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # oppure "gpt-4o" per più precisione
            messages=[
                {"role": "system", "content": "Sei un assistente esperto di analisi di scontrini e OCR."},
                {"role": "user", "content": message_content},
            ],
            temperature=0.2,
        )

        description = response.choices[0].message.content.strip()
        debug_print("modulo ai - analyze_receipt_with_chatgpt - Response: OK", description)
        return description

    except Exception as e:
        debug_print(f"Errore durante la chiamata a ChatGPT: {e}")
        return None

def analyze_folder_products_with_chatgpt(filename, upload_folder):
    # Costruisci il path completo del file
    file_path = f"{upload_folder}/{filename}"

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    content_list = []

    # Legge PDF o immagine
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

    # Prompt per ChatGPT
    question = (
        "Analizza il volantino incluso e restituisci esclusivamente in formato JSON "
        "i primi 10 prodotti alimentari presenti. Per ciascun prodotto includi: "
        "nome_negozio, nome_prodotto, prezzo_originale, prezzo_scontato, "
        "data_inizio_offerta (formato yyyy-mm-dd), data_fine_offerta (formato yyyy-mm-dd). "
        "Se il volantino è del negozio Lidl, le date di validità dell'offerta sono indicate "
        "nella parte alta della prima pagina: applica queste date a tutti i prodotti. "
        "Se non trovi queste date, imposta i campi data_inizio_offerta e data_fine_offerta su null. "
        "Non aggiungere alcun commento, introduzione o spiegazione. Rispondi solo con il JSON."
    )

    # Prepara i contenuti per ChatGPT-4o
    message_content = [{"type": "text", "text": question}]
    for img in content_list:
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        image_b64 = f"data:image/png;base64,{base64.b64encode(buffer.read()).decode()}"
        message_content.append({"type": "image_url", "image_url": {"url": image_b64}})

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # oppure "gpt-4o" se vuoi la versione più potente
            messages=[
                {"role": "system", "content": "Sei un assistente esperto di analisi di volantini e OCR."},
                {"role": "user", "content": message_content}
            ],
            temperature=0.2,
        )

        description = response.choices[0].message.content.strip()
        debug_print("modulo ai - analyze_folder_products_with_chatgpt - Response: OK", description)
        return description

    except Exception as e:
        debug_print(f"Errore durante la chiamata a ChatGPT: {e}")
        return None










'''



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

"""
def analyze_receipt_with_chatgpt(filename, upload_folder):
    # Costruisci il path
    file_path = f"{upload_folder}/{filename}"
    
    #openai.api_key = os.getenv("open_ai_key")  # o inserisci la tua chiave qui direttamente
    
    ocr_text = ""
    
    # Se PDF, estrai tutte le pagine come immagini
    if filename.lower().endswith('.pdf'):
        try:
            doc = fitz.open(file_path)
            for page in doc:
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                text = pytesseract.image_to_string(img, lang="ita")
                ocr_text += text + "\n"
            doc.close()
        except Exception as e:
            print(f"Errore nella lettura del PDF: {e}")
            return None
    else:
        # Se immagine
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang="ita")
            ocr_text += text + "\n"
        except Exception as e:
            print(f"Errore nella lettura dell'immagine: {e}")
            return None

    if not ocr_text.strip():
        print("Nessun testo rilevato dallo scontrino.")
        return None

    # Prompt per ChatGPT
#    prompt = f"""
#Analizza questo scontrino e restituisci solo il risultato in JSON senza testo introduttivo o commenti,
#con nome_negozio (se il negozio è Lidl, restituisci solo Lidl come nome), indirizzo_negozio,
#data_scontrino in formato yyyy-mm-dd, spesa_totale, lista_prodotti con nome_prodotto
#(non aggiungere nella lista prodotti le righe con prezzi negativi oppure i prodotti che iniziano con Statiegeld.
#Il nome_prodotto non deve contenere caratteri come %, ^, !, $ , oppure contenga parole come statiegeld),
#quantita (arrotondata al valore intero più vicino), traduzione_italiano (traduzione sintetica in italiano),
#prezzo_unitario e prezzo_totale (anche se coincidono). Se trovi prezzi negativi, sottrai dal prezzo del prodotto precedente;
#Negli scontrini di Lidl, 'Volkoren ontbijt' e 'Brinta' sono due prodotti diversi.
#Rispondi esclusivamente con il JSON.

#Testo OCR:
#{ocr_text}
#"""
    prompt = f"""Analizza questo scontrino e restituisci solo il JSON richiesto, senza testo introduttivo.
Campi: nome_negozio, indirizzo_negozio, data_scontrino (yyyy-mm-dd), spesa_totale,
lista_prodotti con nome_prodotto (senza %, ^, !, $, né parole come statiegeld), quantita (intero),
traduzione_italiano, prezzo_unitario, prezzo_totale. Se trovi prezzi negativi, sottrai dal prodotto precedente.
Testo OCR:
{ocr_text}
"""
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",  # oppure "gpt-4-turbo"
            messages=[
                {"role": "system", "content": "Sei un esperto nel leggere scontrini e restituire dati strutturati in JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        result_json = response.choices[0].message.content.strip()
        return result_json
    except Exception as e:
        print(f"Errore durante la chiamata a ChatGPT: {e}")
        return None

# Esempio di utilizzo
if __name__ == "__main__":
    filename = "20251022_110839_scontrino.jpg.png"
    UPLOAD_FOLDER = "C:/Percorso/Upload"
    result_json = analyze_receipt_with_chatgpt_3_5(filename, UPLOAD_FOLDER)
    if result_json:
        try:
            parsed = json.loads(result_json)
            print(json.dumps(parsed, indent=4, ensure_ascii=False))
        except json.JSONDecodeError:
            print("Il risultato non è un JSON valido:")
            print(result_json)
    else:
        print("Nessun risultato ottenuto.")

# Configura OpenAI
#openai.api_key = os.getenv("open_ai_key")  # o inserisci la tua chiave qui direttamente



def analyze_receipt_with_chatgpt_3_5(filename, upload_folder):

    file_path = os.path.join(upload_folder, filename)
    
    # Leggi immagine
    try:
        img = Image.open(file_path)
        ocr_text = pytesseract.image_to_string(img, lang="ita")
        if not ocr_text.strip():
            raise ValueError("OCR non ha trovato testo")
    except Exception as e:
        print(f"Errore nella lettura dell'immagine: {e}")
        return None

    # Prompt ottimizzato
    prompt = f"""Analizza questo scontrino e restituisci solo il JSON richiesto, senza testo introduttivo.
Campi: nome_negozio, indirizzo_negozio, data_scontrino (yyyy-mm-dd), spesa_totale,
lista_prodotti con nome_prodotto (senza %, ^, !, $, né parole come statiegeld), quantita (intero),
traduzione_italiano, prezzo_unitario, prezzo_totale. Se trovi prezzi negativi, sottrai dal prodotto precedente.
Testo OCR:
{ocr_text}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        result_json = response.choices[0].message.content.strip()
        print("Analisi completata, JSON ottenuto:")
        print(result_json)
        return result_json
    except Exception as e:
        print(f"Errore durante la chiamata a ChatGPT: {e}")
        return None

'''

#--------------------------------------------------

def validate_receipt_json(json_text):
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"❌ Errore di parsing JSON: {e}")
        return False

    required_fields = ["nome_negozio", "indirizzo_negozio", "data_scontrino", "spesa_totale", "lista_prodotti"]
    for field in required_fields:
        if field not in parsed:
            print(f"❌ Campo mancante: {field}")
            return False

    if not isinstance(parsed["lista_prodotti"], list) or len(parsed["lista_prodotti"]) == 0:
        print("❌ lista_prodotti non valida o vuota")
        return False

    for i, prodotto in enumerate(parsed["lista_prodotti"]):
        for subfield in ["nome_prodotto", "quantita", "prezzo_unitario", "prezzo_totale"]:
            if subfield not in prodotto:
                print(f"❌ Prodotto {i+1} mancante campo: {subfield}")
                return False

    print("✅ JSON valido e completo")
    return True

def extract_json_from_markdown(text):
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()  # fallback se non è markdown


def sanitize_ocr_text(text):
    lines = text.splitlines()
    filtered = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Escludi righe con parole chiave sensibili
        if any(keyword in line.lower() for keyword in ["kaart", "card", "terminal", "aid", "transactie", "merchant", "volgnr", "chip", "cvm"]):
            continue
        # Escludi righe con numeri lunghi (potenziali ID o carte)
        if re.search(r"\b\d{8,}\b", line):
            continue
        filtered.append(line)
    return "\n".join(filtered)

def truncate_after_total(text):
    lines = text.splitlines()
    truncated = []

    for line in lines:
        truncated.append(line)
        # Match esatto su "TOTAAL" come parola intera
        if re.search(r"\bTOTAAL\b", line.upper()):
            print(f"[Truncate] Taglio su: {line}")
            break

    return "\n".join(truncated)



#--- Funzione di analisi scontrino tramite Gemini AI ---
'''
def analyze_receipt_with_gemini(filename, upload_folder):
    import os, io, re, json, fitz
    from PIL import Image
    import pytesseract
    import google.generativeai as genai
    from datetime import datetime

    file_path = os.path.join(upload_folder, filename)
    trace_path = os.path.join(upload_folder, "process.log")

    def writelog(message):
        """Scrive un messaggio nel log con timestamp"""
        with open(trace_path, "a") as log:
            log.write(f"[{datetime.now().isoformat()}] {message}\n")
            log.flush()

    def extract_text_from_pdf(path):
        try:
            doc = fitz.open(path)
            full_text = ""
            for page_num, page in enumerate(doc):
                pix = page.get_pixmap(dpi=300)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                text = pytesseract.image_to_string(img, lang="ita+eng+nld")
                full_text += f"\n--- Pagina {page_num + 1} ---\n{text}"
            doc.close()
            writelog("Step: OCR PDF completato")
            return full_text.strip()
        except Exception as e:
            writelog(f"Step: Errore OCR PDF - {e}")
            debug_print(f"❌ Errore OCR PDF: {e}")
            return None

    def extract_text_from_image(path):
        try:
            img = Image.open(path)
            text = pytesseract.image_to_string(img, lang="ita+eng+nld")
            writelog("Step: OCR immagine completato")
            return text.strip()
        except Exception as e:
            writelog(f"Step: Errore OCR immagine - {e}")
            debug_print(f"❌ Errore OCR immagine: {e}")
            return None

    def extract_json_from_markdown(text):
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        return text.strip()

    # --- Inizio procedura ---
    writelog("\n--- New analyze_receipt run ---")
    writelog(f"File path: {file_path}")

    debug_print(f"Analisi scontrino con Gemini: {file_path}")

    # OCR
    writelog("Step: OCR started")
    if filename.lower().endswith(".pdf"):
        ocr_text = extract_text_from_pdf(file_path)
    else:
        ocr_text = extract_text_from_image(file_path)
    writelog("Step: OCR finished")

    if not ocr_text:
        writelog("Step: OCR non ha trovato testo")
        debug_print("❌ OCR non ha trovato testo")
        return None

    # Sanitize OCR
    try:
        ocr_text = sanitize_ocr_text(ocr_text)
        ocr_text = truncate_after_total(ocr_text)
    except Exception as e:
        writelog(f"Step: Errore durante sanitizzazione OCR - {e}")
        debug_print(f"❌ Errore sanitizzazione OCR: {e}")
        return None

    debug_print("\n" + "="*40)
    debug_print("     Testo OCR sanitizzato da inviare a Gemini:")
    debug_print(ocr_text)
    debug_print("="*40 + "\n")

    # --- Chiamata Gemini ---
    gemini_api_key = os.getenv("gemini_api_key")
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-2.5-pro')

    prompt = f"""Analizza questo scontrino e restituisci solo il JSON richiesto, senza testo introduttivo.
Campi: nome_negozio, indirizzo_negozio, data_scontrino (yyyy-mm-dd), spesa_totale,
lista_prodotti con nome_prodotto (senza %, ^, !, $, né parole come statiegeld), quantita (intero),
traduzione_italiano, prezzo_unitario, prezzo_totale. Se trovi prezzi negativi, sottrai dal prodotto precedente.
Testo OCR:
{ocr_text}
"""

    try:
        writelog("Step: Gemini request started")
        debug_print("Chiama Gemini per analisi scontrino...")

        response = model.generate_content([prompt])

        writelog("Step: Gemini response received")
        debug_print(f"Chiamata Gemini completata. Tipo risposta: {type(response)}")

        raw_text = response.text
        if not raw_text or not isinstance(raw_text, str):
            writelog("Step: Nessuna risposta testuale da Gemini")
            debug_print("❌ Nessuna risposta testuale da Gemini")
            return None

        cleaned = extract_json_from_markdown(raw_text)
        try:
            parsed = json.loads(cleaned)
            writelog("Step: JSON parsing completato")
        except Exception as e:
            writelog(f"Step: Errore parsing JSON - {e}")
            debug_print(f"❌ Errore parsing JSON: {e}")
            return None

        if not validate_receipt_json(cleaned):
            writelog("Step: JSON non valido")
            debug_print("❌ JSON non valido")
            return None

        writelog("Step: Analisi completata con successo ✅")
        debug_print("✅ JSON restituito da Gemini:")
        debug_print(json.dumps(parsed, indent=2))

        return parsed

    except Exception as e:
        writelog(f"Step: Errore durante la chiamata a Gemini - {e}")
        debug_print(f"❌ Errore durante la chiamata a Gemini: {e}")
        return None

    finally:
        writelog("Step: Fine analisi\n")
'''