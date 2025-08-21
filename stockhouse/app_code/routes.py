from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify
from stockhouse.app_code.barcode import lookup_barcode
from stockhouse.app_code.models import add_product_dim, add_transaction_fact, delete_product_from_db,  lookup_products, get_all_products, get_all_shops, get_all_categories, get_all_items, lookup_products_by_name,\
                       lookup_products_by_name_ins_date, update_product_dim, get_priority_level, get_product_inventory, get_product_inventory_by_barcode, upsert_inventory, search_unconsumed_products_db, \
                       lookup_category_by_item, update_transaction_fact, update_transaction_fact_consumed, get_products_by_name, get_expiring_products, insert_consumed_fact, \
                       get_number_expiring_products, get_out_of_stock_count, get_critical_stock_count, get_monthly_consumed_count, \
                       get_week_date_range, get_product_by_name_and_dates, get_expiring_products_for_home, get_out_of_stock_products, get_critical_stock, get_monthly_consumed_statistics, \
                       upsert_budget, get_budget, update_inventory_mean_usage_time, get_unconsumed_products_full_list,  \
                       get_unique_unconsumed_record, clean_old_transactions, update_reorder_frequency,upsert_expense, delete_from_shopping_list, upsert_transaction_fact
from stockhouse.app_code.models import add_shop, update_shop, delete_shop, get_unknown_products, delete_unknown_product_by_name, insert_product_alias_if_not_exists  
from stockhouse.app_code.models import add_category, get_all_categories, update_category, delete_category, get_all_items, update_item, delete_item
import sqlite3
import hashlib
from datetime import datetime, date
from config import Config  # usa il path corretto se è diverso
from flask import send_from_directory
import os
from config import Config
from stockhouse.utils import debug_print
from stockhouse.app_code.shopping_list_utils import (
    get_current_week,
    get_week_date_range,
    is_last_week_with_25,
    get_shopping_list_data,
    get_spesa_per_decade,
    get_budget_info,
    process_shopping_queue,
    get_reorder_count_from_shopping_list,
    get_reorder_total_cost,
    get_suggested_products,
    get_current_decade,
    format_decade_label,
    set_refresh_needed,
    is_refresh_needed,
    get_aliases_from_db,
    fuzzy_match_product,
    insert_unknown_product,
    normalize_text,
    remove_from_shopping_lst,
    trigger_thread_on_exit)

from stockhouse.app_code.ai import manage_shopping_receipt, analyze_receipt_with_gemini, fetch_shopping_list

import calendar
from calendar import month_name
import json
import re
import traceback

main = Blueprint('main', __name__)


# Cartella di lavoro per scontrini (development)
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploaded_receipts')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@main.route('/')
def homepage():
    decade_number = get_current_decade()
    debug_print(f"Decade number: {decade_number}")
    current_decade_label = format_decade_label(decade_number)
    debug_print(f"Current decade: {current_decade_label}")
    return render_template('home.html', current_decade=current_decade_label)


@main.route('/api/system/db-changed-time')
def fake_db_changed_time():
    return jsonify({
        "changed": "2025-04-19T16:00:00Z"  # data finta, oppure dinamica
    })

#Converte il path locale in uno relativo per il browser
@main.route('/images/<filename>')
def serve_image(filename):
    image_folder = Config.get_image_folder()
    return send_from_directory(image_folder, filename)

# Visualizza l'Home page
@main.route('/')
def home():

    week_number = get_current_week()
    # Calcola l'intervallo di date per la settimana
    start_date, end_date = get_week_date_range(week_number)

    if start_date is None or end_date is None:
        return render_template(
            'home.html',
            week_number=week_number,
            start_date="Settimana non valida",
            end_date=""
        )

    debug_print(f"Week: {week_number}, start_date, end_date: {start_date}, {end_date}")
    return render_template(
        'home.html',
        week_number=week_number,
        start_date=start_date.strftime('%A %d %B %Y'),
        end_date=end_date.strftime('%A %d %B %Y')
    )





#Chiamata dallo script in index.html
@main.route("/lookup", methods=["GET"])
def lookup():
    barcode = request.args.get("barcode")
    name = request.args.get("name")

    # 1️⃣ Se c'è un barcode, proviamo a cercare localmente
    if barcode:
        prodotto_esistente = lookup_products(barcode=barcode)
        if prodotto_esistente["found"]:
            debug_print("lookup barcode: ", prodotto_esistente)
            return jsonify(prodotto_esistente)

    # 2️⃣ Se non trovato o non c'è barcode, ma c'è il nome, cerca localmente per nome
    if name:
        prodotto_per_nome = lookup_products_by_name(name)
        if prodotto_per_nome["found"]:
            debug_print("lookup per nome: ", prodotto_per_nome)
            return jsonify(prodotto_per_nome)


    # 3️⃣ Se c'è barcode e non abbiamo ancora trovato nulla, cerca online
    if barcode:
       data = lookup_barcode(barcode)
       debug_print("lookup online: ", data)
       if "error" not in data:
           image_path = data.get("image", None)
        
           # Se l'immagine è salvata localmente, converti il path assoluto in uno relativo per il browser
           if image_path and os.path.exists(image_path): 
               image_filename = os.path.basename(image_path)
               image_url = f"/images/{image_filename}"
           else:
               image_url = None  # Nessuna immagine o path non valido

           return jsonify({
               "found": True,
               "name": data["name"],
               "brand": data["brand"],
               "quantity": 0,
               "image": image_url
           })


    # 4️⃣ Niente trovato
    return jsonify({"found": False, "error": "Prodotto non trovato"})


@main.route("/lookup_online/<barcode>")
def lookup_online(barcode):
    data = lookup_barcode(barcode)  # Funzione che cerca online
    if "error" not in data:
        return jsonify({
            "found": True,
            "name": data["name"],
            "brand": data["brand"],
            "quantity": 1,
            "image": data.get("image", "")
        })
    else:
        return jsonify({"found": False})


# Funzione per generare MD5
def generate_md5(barcode, ins_date, index):
    # Combina barcode, ins_date e l'indice per creare una stringa unica
    string = f"{barcode}_{ins_date}_{index}"
    # Restituisci l'MD5 della stringa
    return hashlib.md5(string.encode()).hexdigest()


# E`la route della pagina principale dedicata all'inserimento di prodotti
# Serve anche per popolare la seconda tab
@main.route('/index', methods=["GET", "POST"])
def index():
    
    debug_print(f" Routes: Metodo richiesta: {request.method}")  # 🔍 Controllo se arriva POST o GET
    new_product = None
    if request.method == "POST":
       
        # Ottiene i valori dei campi salvati nel form di inserimento
        barcode = request.form["barcode"]
        name = request.form["name"]
        brand = request.form["brand"]
        shop = request.form.get("shop")
        price = request.form.get("price")
        quantity = int(request.form.get("quantity"))
        consumed_quantity = 0
        category = request.form.get("category")
        item = request.form.get("item")
        expiry_date = request.form.get("expiry_date")
        image = request.form.get("image") or None

        debug_print("index -> POST", barcode,name,brand,shop,price,quantity,category,item,expiry_date )

        # Ottieni la data odierna e formatta come yyyy-mm-dd
        ins_date     = datetime.now().strftime('%Y-%m-%d')
        consume_date = None
        status       = 'in stock'
        product_key  = None
        
        # Verifica se il prodotto e` presente in product_dim usando name, poiche barcode puo anche essere null
        prodotto_esistente = lookup_products_by_name(name)

        debug_print(f"Risultato lookup DB: {prodotto_esistente}")

        if prodotto_esistente and prodotto_esistente["found"]:
            product_key = prodotto_esistente["id"]  
            name        = prodotto_esistente["name"]
            brand       = prodotto_esistente["brand"]
            shop        = prodotto_esistente["shop"]
            category    = prodotto_esistente["category"]
            item        = prodotto_esistente["item"]
            image       = prodotto_esistente["image"]
            debug_print("index -> POST 2", barcode,name,brand,shop,price,quantity,category,item )
        else:
            # Il prodotto non e` presente in product_dim, cerca online con il barcode
            data = lookup_barcode(barcode)
            debug_print("index -> POST 3", barcode,name,brand,shop,price,quantity,category,item )
            if "error" not in data:
                name = data["name"]
                brand = data["brand"]
                quantity = quantity if quantity else data["quantity"]  # ✅ Mantiene il valore inserito, a meno che non sia vuoto
                consumed_quantity = 0  # Inizializza a 0 se non esiste
                image = data.get("image", None)
                debug_print("index -> POST 4", barcode,name,brand,shop,price,quantity,category,item )

            # INSERT in product_dim anche se il barcode e` null oppure non e`stato trovato online
            debug_print ("index -> add_product_dim: ", barcode, name, brand, shop, category, item, image)      
            result = lookup_category_by_item(item)

            # Associare il risultato alla variabile 'category' se trovato
            if result["found"]:
                category = result["category"]
                debug_print(f"La categoria dell'item '{item}' è: {category}")
            else:
                debug_print(f"Item '{item}' non trovato.")

            # INSERT in product_dim anche se il barcode e` null oppure non e`stato trovato online
            debug_print ("index -> add_product_dim: ", barcode, name, brand, shop, category, item, image)      
        
            # Prepara l'immagine per il DB         
            if barcode:
                # Ottieni l'URL base per le immagini
                image_url = Config.get_image_url()
                # Costruisci il nome del file immagine
                image_filename = f"{barcode}.jpg"
                # Percorso assoluto dell'immagine sul filesystem
                image_path = os.path.join(Config.get_image_folder(), image_filename)

                debug_print(f"[DEBUG] image_url: {image_url}")
                debug_print(f"[DEBUG] image_filename: {image_filename}")
                debug_print(f"[DEBUG] image_path: {image_path}")

                if os.path.exists(image_path):
                    # Percorso per il browser (Home Assistant espone /config/www come /local)
                    image_browser_path = f"{image_url}/{image_filename}"
                    debug_print(f"[DEBUG] image_browser_path: {image_browser_path}")
                else:
                    # Se l'immagine non esiste, nessun percorso per il browser
                    image_browser_path = None
                    debug_print("[WARNING] Immagine non trovata.")
            else:
                # Nessun barcode, nessun percorso immagine
                image_browser_path = None
                debug_print("[INFO] Nessun barcode fornito.")

            debug_print("index -> add_product_dim: ", image_path)

            # Il nome e`comunque quello impostato nel form! 
            name = request.form["name"]
            debug_print("index -> add_product_dim: ", barcode, name, brand, shop, category, item, image_browser_path)
            add_product_dim(barcode, name, brand, shop, category, item, image_browser_path)

        # Ottiene ID del prodotto
        if product_key is None:
           prodotto_esistente=lookup_products_by_name(name)
           product_key = prodotto_esistente["id"]    
 
        # Salva la tranasazione
        add_transaction_fact(product_key, barcode, price, quantity, consumed_quantity, ins_date, consume_date, expiry_date, status)
        flash("Prodotto aggiunto o aggiornato!", "success")

        # Aggiorna exspenses_fact
        selected_decade = get_current_decade()
        price = float(price)
        quantity = int(quantity)
        amount = price * quantity
        rounded_amount = round(amount, 2)  # Arrotonda a 2 decimali

        # Se il prodotto è stato aggiunto alla lista della spesa, lo rimuoviamo
        debug_print("index -> delete_from_shopping_list: ", barcode)
        delete_from_shopping_list(barcode)

        # cancella il prodotto da unknown_products, se presente
        delete_unknown_product_by_name(name)

        # crea un nuovo alias per il prodotto, se non esiste già
        insert_product_alias_if_not_exists(name, barcode, shop)

        # Aggiorna lo stato del refresh che verra eseguito all'apertura della pagina shopping_list che puo avvenire anche da Shoppy
        set_refresh_needed(True)

        conn = sqlite3.connect(Config.DATABASE_PATH)
        cursor = conn.cursor()
        upsert_expense(cursor, ins_date, selected_decade, shop, rounded_amount)  
        conn.commit()
        conn.close()
         

        # Prepara un dizionario con i dati del prodotto appena inserito
        new_product = {
            "barcode": barcode,
            "name": name,
            "brand": brand,
            "shop": shop,
            "price": price,
            "quantity": quantity,
            "consumed_quantity": consumed_quantity,
            "category": category,
            "item": item,
            "expiry_date": expiry_date 
            }

    # 💡 Se la richiesta è GET, semplicemente carichiamo la pagina
    products      = get_all_products()
    debug_print("ALL PRODUCTS: ", products)
    shops         = get_all_shops()
    #debug_print("ALL SHOPS: ", shops)
    categories    = get_all_categories()
    items = get_all_items()

    return render_template("index.html",
                        products=products,
                        shops=shops,
                        categories=categories,
                        items=items,
                        new_product=new_product,
                        active_tab='add')



# Questa route viene chiamata quando si clicca sul pulsante Elimina Prodotto dalla pagina di gestione dei prodotti
@main.route('/delete_product/<barcode>/<ins_date>')
def delete_product(barcode, ins_date):
    delete_product_from_db(barcode, ins_date)
    flash("Prodotto eliminato.", "success")
    return redirect(url_for('main.index') + '#manage')


# ✅ Nuova route per la lista prodotti nel magazzino
@main.route('/inventory')
def list_inventory():

    clean_old_transactions                  # 🧽 Step 1: pulizia
    update_inventory_mean_usage_time()      # 🧠 Step 2: calcolo mean_usage_time
    update_reorder_frequency()              # 🔄 Step 3: calcolo reorder_frequency
    products = get_product_inventory()      # 🏭 Step 4 - Seleziona i records per l'inventario

    debug_print ("Show_Product in inventory: ", products)

    return render_template("inventory.html", products=products)


# Questa procedura viene chiamata dal metodo POST dopo aver cliccato sul pulsante Modifica Parametri di Magazzino
# Per inserire oppure modificare un record esistente nella tabella product_dim
@main.route('/products/update_inline', methods=['POST'])
def update_products_inline():
    data = request.get_json()
    barcode = data.get('barcode')
    allowed_fields = [
        'necessity_level', 'season', 'min_quantity', 'max_quantity',
        'security_quantity', 'reorder_point', 'mean_usage_time',
        'reorder_frequency', 'user_override'
    ]

    updates = []
    values = []

    # Prepara i campi per l'UPDATE SQL
    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            values.append(data[field])

    # Se abbiamo necessity_level e season, calcoliamo priority usando tutti i dati ricevuti
    necessity_level = data.get('necessity_level')
    product_seasons = data.get('season')

    if necessity_level is not None and product_seasons is not None:
        priority_level = get_priority_level(
            barcode,
            necessity_level,
            product_seasons,
            override_data=data  # <-- tutti i valori passati qui
        )
        updates.append("priority_level = ?")
        values.append(priority_level)

    if not updates:
        return jsonify(success=False, error="Nessun campo da aggiornare")

    values.append(barcode)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE product_settings SET {', '.join(updates)} WHERE barcode = ?", values)
    conn.commit()
    conn.close()

    return jsonify(success=True, priority_level=priority_level if 'priority_level' in locals() else None, barcode=barcode)

# Questa route serve per visualizzare il filtro modale dell'ins_date nella seconda tab dei prodotti
@main.route('/products/ins_dates')
def get_ins_dates():
    barcode = request.args.get('barcode')
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT tf.ins_date FROM product_dim pd JOIN transaction_fact tf ON pd.barcode=tf.barcode WHERE pd.barcode = ?", (barcode,))
    ins_dates = [row['ins_date'] for row in cur.fetchall()]
    conn.close()
    return jsonify(ins_dates)

@main.route("/edit/<barcode>/<ins_date>", methods=["GET", "POST"])
#La procedura viene chiamata da Prodotti--> Modifica/Rimuovi Prodotta al momento del click sul pulsaante Modifica
# Il metodo GET serve a riempire il form con i dati relativi il prodotto selezionato
# Il metodo POST serve per attivare la modifica nel Database
def edit_product(barcode, ins_date):
    # Recupera i dettagli del prodotto dal database per il form di modifica
    debug_print("edit_product: ", barcode, ins_date)
    debug_print("requested method: ", request.method)

    product    = lookup_products_by_name_ins_date(barcode,ins_date)
    id = product["id"]
    shop_list  = get_all_shops()
    items = get_all_items()
    #debug_print("requested method: ", product)
    debug_print("edit product intero record: ", product)

    if request.method == "POST":
        # Modifica i dati del prodotto
        barcode = request.form["barcode"]
        name = request.form["name"]
        brand = request.form["brand"]
        shop = request.form["shop"]
        price = request.form["price"]
        quantity = request.form["quantity"]
        item = request.form["item"]
        ins_date = request.form["ins_date"]
        expiry_date = request.form["expiry_date"]

        
        # Salva il prodotto modificato nel database
        #debug_print ("update_product: ", barcode, name, brand, shop, item, ins_date)
        category = lookup_category_by_item(item)
        update_product_dim(id, name, brand, shop, category, item)
        update_transaction_fact(id, price, quantity,  expiry_date, ins_date)
        flash("Prodotto aggiornato con successo!", "success")
        return redirect(url_for('main.index') + '#manage')  # Torna alla lista dei prodotti dopo il salvataggio
    

    return render_template("edit_product.html", product=product, shop_list=shop_list, items=items)


@main.route('/products/unconsumed')
def search_unconsumed_products():
    query = request.args.get('q', '')
    debug_print("Route - unconsumed products1: ", query)
    
    # Chiamata alla funzione nel modello
    results = search_unconsumed_products_db(query)
    
    debug_print("Route - unconsumed products2: ", results)
    return jsonify(results)

# Questa route serve per visualizzare i prodotti non consumati filtrati dal menu a tendina (tab3)
@main.route('/products/unconsumed_dropdown', methods=['GET'])
def unconsumed_dropdown():
    products = get_unconsumed_products_full_list()
    return jsonify(products)

# Questa route serve per visualizzare esclusivamente il prodotto non consumato filtrato dal dropdown menu (tab3) 
@main.route('/consumed/get_by_unique', methods=['GET'])
def get_single_unconsumed_product():
    barcode = request.args.get('barcode')
    ins_date = request.args.get('ins_date')
    expiry_date = request.args.get('expiry_date')  # Può essere "null"

    if not barcode or not ins_date:
        return jsonify({'success': False, 'error': 'Dati insufficienti'}), 400

    product = get_unique_unconsumed_record(barcode, ins_date, expiry_date)

    if product:
        return jsonify({'success': True, 'data': [product]})
    else:
        return jsonify({'success': False, 'data': []})




@main.route('/consumed_product', methods=['GET', 'POST'])
def consumed_product():
    id = request.args.get('id')
    product_key = request.args.get('product_key')
    barcode = request.args.get('barcode')
    ins_date = request.args.get('ins_date')
    expiry_date = request.args.get('expiry_date')
    quantity = int(request.args.get('quantity'))

    debug_print("Route: /consumed_product/", id, product_key, barcode, quantity, ins_date, expiry_date)

    update_transaction_fact_consumed(id, ins_date, expiry_date)

    #Registra il consumo in consume_fact
    insert_consumed_fact (product_key, barcode, ins_date, expiry_date)
    
    # Calcola la quantità totale aggiornata a magazzino per quel barcode
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT SUM(quantity - COALESCE(consumed_quantity, 0)) 
        FROM transaction_fact
        WHERE barcode = ? AND status = 'in stock'
    """, (barcode,))
    total_quantity = cur.fetchone()[0]
    
    if total_quantity == 0:
        new_status = 'out of stock'
        consume_date = datetime.date.today() 
    else:
        new_status = 'in stock'
        consume_date = None
    
    conn.close()


    return jsonify(success=True, quantita=total_quantity, status=new_status, consumo=consume_date)

@main.route('/consumed/get_records', methods=["GET"])
def get_records():
    # Ottieni i parametri dalla richiesta
    name = request.args.get('name')  # Nome del prodotto
    barcode = request.args.get('barcode') # Barcode del prodotto
    ins_date = request.args.get('ins_date')  # Data di inserimento
    expiry_date = request.args.get('expiry_date')  # Data di scadenza (può essere NULL)

    # Debugging: stampa i parametri ricevuti
    #debug_print("get_records - name: ", name)
    #debug_print("get_records - barcode: ", barcode)
    #debug_print("get_records - Data di inserimento: ", ins_date)
    #debug_print("get_records - Data di scadenza: ", expiry_date)

    # Verifica che il parametro 'nome' sia presente
    if not name:
        return jsonify({"error": "Parametro 'name' mancante"}), 400
    
    # Verifica che il barcode sia presente
    #if not barcode:
    #    return jsonify({"error": "Parametro 'barcode' mancante"}), 400

    # Verifica che la data di inserimento sia presente
    if not ins_date:
        return jsonify({"error": "Parametro 'ins_date' mancante"}), 400

    # Chiamata alla funzione nel modello
    result = get_product_by_name_and_dates(name, ins_date, expiry_date)

    # Se non ci sono risultati, restituisci un errore
    if not result:
        return jsonify({"error": f"Nessun prodotto trovato per '{name}' con ins_date '{ins_date}' e expiry_date '{expiry_date}'"}), 404

    debug_print("get_records - Risultati trovati: ", result)

    return jsonify({"success": True, "data": result})

@main.route('/shops', methods=["GET", "POST"])
def shops():
    last_shop = None  # ← per salvare solo l'ultimo negozio inserito

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        note = request.form.get("note", "").strip()
        if nome:
            add_shop(nome, note)
            flash("Negozio salvato con successo!", "success")
            # Recupera l'ultimo negozio appena inserito
            conn = sqlite3.connect(Config.DATABASE_PATH)
            c = conn.cursor()
            c.execute("SELECT id, name, note FROM shop_list ORDER BY id DESC LIMIT 1")
            last_shop = c.fetchone()
            conn.close()
        else:
            flash("Il nome del negozio è obbligatorio.", "error")

    # Sempre recupera la lista completa per la seconda tab
    shop_list = get_all_shops()

    return render_template("shops.html", shop_list=shop_list, last_shop=last_shop)


@main.route('/edit_shop/<int:shop_id>', methods=['GET', 'POST'])
def edit_shop(shop_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['name']
        notes = request.form['notes']
        update_shop(shop_id, name, notes)
        conn.close()
        flash('📝 Negozio aggiornato con successo!', 'success')
        return redirect(url_for('main.shops'))
    
    c.execute("SELECT id, name, note FROM shop_list WHERE id = ?", (shop_id,))
    shop = c.fetchone()
    conn.close()
    if shop:
        return render_template('edit_shop.html', shop=shop)
    else:
        flash('❌ Negozio non trovato.', 'danger')
        return redirect(url_for('main.shops'))

@main.route('/delete_shop/<int:shop_id>', methods=['POST'])
def delete_shop_route(shop_id):
    delete_shop(shop_id)
    flash('🗑️ Negozio eliminato con successo!', 'success')
    return redirect(url_for('main.shops'))

@main.route('/categories', methods=["GET", "POST"])
def categories():
    last_category = None  # 👈 Per mostrare l'ultima inserita solo nella prima tab

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        note = request.form.get("note", "").strip()
        if nome:
            try:
                add_category(nome, note)
                flash("Categoria salvata con successo!", "success")
                last_category = (nome, note)  # 👈 Memorizza l'ultima categoria inserita
            except sqlite3.IntegrityError:
                flash("⚠️ La categoria esiste già!", "error")
        else:
            flash("⚠️ Il nome della categoria è obbligatorio.", "error")

    categories = get_all_categories()
    return render_template("categories.html", categories=categories, last_category=last_category)



@main.route('/edit_category/<int:category_id>', methods=['GET', 'POST'])
def edit_category(category_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        note = request.form['note']
        try:
            update_category(category_id, name, note)
            flash('✅ Categoria aggiornata con successo!', 'success')
        except sqlite3.IntegrityError:
            flash("❗ Esiste già una categoria con questo nome.", "error")
        return redirect(url_for('main.categories'))

    c.execute("SELECT id, name, note FROM category_list WHERE id = ?", (category_id,))
    category = c.fetchone()
    conn.close()
    return render_template('edit_category.html', category=category)


@main.route('/delete_category/<int:category_id>', methods=['POST'])
def delete_category_route(category_id):  # 🔁 Cambia nome alla funzione route per evitare conflitti
    delete_category(category_id)  # ✅ Questa è la funzione del modello
    flash('🗑️ Categoria eliminata con successo!', 'success')
    return redirect(url_for('main.categories'))

@main.route('/items', methods=["GET", "POST"])
def items():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # Recupera le categorie
    cursor.execute("SELECT id, name FROM category_list")
    categories = cursor.fetchall()

    # Esempio: gestione post + recupero ultima subcategoria inserita (opzionale)
    last_item = None
    if request.method == "POST":
        nome = request.form["nome"]
        note = request.form.get("note", "")
        category_id = request.form["category"]
       
        cursor.execute("INSERT INTO item_list (name, note, category_id) VALUES (?, ?, ?)", (nome, note, category_id))

        conn.commit()

        cursor.execute("SELECT id, name, note FROM category_list WHERE id = ?", (category_id,))
        category = cursor.fetchone()
        category_name = category[1]
        conn.close()
 
        last_item = (nome, note, category_name)

    conn.close()

    items = get_all_items()  # ✅ usa la funzione già pronta
    return render_template("items.html", categories=categories, items=items,last_item=last_item)


@main.route('/edit_item/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    # Recupera le categorie
    c.execute("SELECT id, name FROM category_list")
    categories = c.fetchall()
    debug_print("edit_item: ", request.method)

    if request.method == 'POST':
        debug_print("edit_item: ", request.form['name'], request.form['note'], request.form['category'])
        name     = request.form['name']
        category_id = request.form['category']
        note     = request.form['note']
        
        try:         
            update_item(item_id, name, note,  category_id)
            flash('✅ Sub Categoria aggiornata con successo!', 'success')
        except sqlite3.IntegrityError:
            flash("❗ Esiste già una sub categoria con questo nome.", "error")
        return redirect(url_for('main.items'))

    c.execute("SELECT id, name, category_id, note FROM item_list WHERE id = ?", (item_id,))

    
    item = c.fetchone()
    debug_print("item: ", item)
    conn.close()
    return render_template('edit_item.html', categories=categories, item=item)


@main.route('/delete_item/<int:item_id>', methods=['POST'])
def delete_item_route(item_id):  # 🔁 Cambia nome alla funzione route per evitare conflitti
    delete_item(item_id)  # ✅ Questa è la funzione del modello
    flash('🗑️ Sub Categoria eliminata con successo!', 'success')
    return redirect(url_for('main.items'))

#questa route serve per visualizzare i prodotti in via di scadenza 
@main.route('/expiring_products')
def expiring_products():
    # Ottieni il parametro "months" dalla query string (default: 1 mese)
    months = int(request.args.get('months', 1))
    debug_print(f"Filtro mesi: {months}")

    # Recupera i prodotti in scadenza entro il numero di mesi specificato
    products = get_expiring_products(months)

    # Messaggio da mostrare se non ci sono risultati
    message = None
    if not products:
        message = f"Nessun prodotto in scadenza trovato entro {months} mese/i."

    # Renderizza la pagina HTML con i prodotti filtrati e il messaggio
    return render_template('expiring_products.html', products=products, message=message)

# Questa route serve per visualizzare i prodotti in scadenza nella home page
@main.route('/home_expiring_products', methods=['GET'])
def home_expiring_products():
    # Ottieni il parametro "months" dalla query string (default: 1 mese)
    months = int(request.args.get('months', 1))
    debug_print(f"home_expiring_products - Filtro mesi: {months}")

    # Recupera i prodotti in scadenza entro il numero di mesi specificato
    products = get_expiring_products_for_home()
    debug_print("home_expiring_products - Prodotti in scadenza: ", products)

    # Se non ci sono prodotti, restituisci un messaggio vuoto
    if not products:
        return jsonify({
            "headers": ["Nome", "Barcode", "Data di Scadenza", "Quantità"],
            "records": [],
            "message": f"Nessun prodotto in scadenza trovato entro {months} mese/i."
        })

    # Restituisci i dati come JSON
    return jsonify({
        "headers": ["Nome", "Barcode", "Data di Scadenza", "Quantità"],
        "records": [[p["name"], p["barcode"], p["expiry_date"], p["quantity"]] for p in products]
    })

# Questa route serve per visualizzare i prodotti esauriti
@main.route('/home_out_of_stock_products', methods=['GET'])
def home_out_of_stock_products():
    # Recupera i prodotti esauriti
    products = get_out_of_stock_products()
    debug_print("home_out_of_stock_products - Prodotti esauriti: ", products)

    # Se non ci sono prodotti, restituisci un messaggio vuoto
    if not products:
        return jsonify({
            "headers": ["Nome", "Barcode", "Categoria"],
            "records": [],
            "message": "Nessun prodotto esaurito trovato."
        })

    # Restituisci i dati come JSON
    return jsonify({
        "headers": ["Nome", "Barcode", "Categoria"],
        "records": [[p["name"], p["barcode"], p["category"]] for p in products]
    })


# Questa funzione restituisce la decade corrente in base alla data odierna
def get_decade_period_label(decade_code):
    today = datetime.today()
    month = today.month
    year = today.year
    month_label = month_name[month]
    last_day = calendar.monthrange(year, month)[1]

    if decade_code == "D1":
        return f"1 {month_label} - 10 {month_label} {year}"
    elif decade_code == "D2":
        return f"11 {month_label} - 20 {month_label} {year}"
    else:
        return f"21 {month_label} - {last_day} {month_label} {year}"
    
# Questa route serve per visualizzare la lista della spesa
@main.route('/shopping_list')
def shopping_list():
    selected_decade = get_current_decade()
    debug_print("Decade selezionata: ", selected_decade)

    refresh_needed = 1  #is_refresh_needed()
    debug_print("Flag refresh_needed: ", refresh_needed)

    if refresh_needed:
        debug_print("⚠️ Rigenerazione necessaria. Ricreo la shopping_list.")
        items, shop_totals = get_shopping_list_data(save_to_db=True, decade=selected_decade)
        set_refresh_needed(False)
    else:
        debug_print("✅ Nessuna rigenerazione. Uso la lista salvata.")
        items, shop_totals = get_shopping_list_data(save_to_db=False, decade=selected_decade)

    suggested_items = get_suggested_products()
    period_label = get_decade_period_label(selected_decade)
    budget_record = get_budget_info()
    spesa_decade = get_spesa_per_decade()

    budget = float(budget_record['budget']) 
    spesa_corrente = sum(spesa_decade)
    budget_residuo = round(budget - spesa_corrente, 2)
    debug_print("shopping_list Budget: ", budget, budget_record)

    debug_print("Spesa corrente: ", [dict(item) for item in items])

    return render_template(
        'shopping_list.html',
        items=items,
        shop_totals=shop_totals,
        selected_decade=selected_decade,
        suggested_items=suggested_items,
        budget_record=budget_record,
        spesa_decade=spesa_decade,
        budget=budget,
        spesa_corrente=spesa_corrente,
        budget_residuo=budget_residuo,
        current_decade=selected_decade,
        period_label=period_label
    )


@main.route('/shopping_list/add_selected', methods=['POST'])
def add_selected_products():
    try:
        data = request.get_json()
        debug_print("🔍 Dati ricevuti:", data)

        barcodes = data.get('barcodes')
        if not barcodes:
            return "Nessun barcode ricevuto", 400

        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for barcode in barcodes:
            # Verifica se è già nella lista
            cursor.execute("SELECT 1 FROM shopping_list WHERE barcode = ?", (barcode,))
            if cursor.fetchone():
                continue
            debug_print("add_selected_products - barcode: ", barcode)       

            # Recupera i dati per quel barcode
            cursor.execute("""
                SELECT pd.name, pd.shop, tf.price
                FROM product_dim pd
                JOIN (
                    SELECT barcode, price
                    FROM (
                        SELECT barcode, price, ins_date,
                            ROW_NUMBER() OVER (PARTITION BY barcode ORDER BY ins_date DESC) AS rn
                        FROM transaction_fact
                    ) AS ranked
                    WHERE rn = 1
                ) AS tf ON pd.barcode = tf.barcode
                WHERE pd.barcode = ?
            """, (barcode,))

            row = cursor.fetchone()
            if not row:
                continue  # se il barcode non esiste in product_dim, salta

            # Inserisce nella lista

            current_decade = get_current_decade(datetime.today())
            within_budget = 1 # E` stato aggiunto manualmente, quindi lo si vuole comprare
            current_date = datetime.today().date()
            reason_to_add = "Aggiunto manualmente"
            debug_print("add_selected_products - Dati da inserire:", barcode, row["name"], row["shop"], row["price"], current_decade)
            try:
               cursor.execute("""
                    INSERT INTO shopping_list (
                        barcode, product_name, quantity_to_buy, shop, reason, price, decade_number, insert_date, within_budget
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (barcode, row["name"], 1, row["shop"], reason_to_add, row["price"], current_decade, current_date, within_budget))

            except Exception as insert_error:
                debug_print("❌ Errore durante INSERT:", str(insert_error))

        conn.commit()
          
        # Ricarica la nuova lista 
        cursor.execute("""
            SELECT barcode, product_name, quantity_to_buy, shop, reason, price
            FROM shopping_list
            WHERE within_budget=1 AND decade_number = ?  
            ORDER BY shop, product_name
        """, (current_decade,))

        updated_items = cursor.fetchall()
        updated_items = [dict(row) for row in updated_items]

        # Calcolo totali per negozio
        shop_totals = {}
        for item in updated_items:
            shop = item.get("shop")
            if not shop:
                continue
            product_cost = item["price"] * item["quantity_to_buy"]
            shop_totals.setdefault(shop, 0)
            shop_totals[shop] += product_cost

        conn.close()

        debug_print("add_selected_products - Lista aggiornata:", updated_items)
        debug_print("add_selected_products - Totali per negozio:", shop_totals)
        print(updated_items)
        print(shop_totals)

        #return render_template('shopping_list_table.html', items=updated_items, shop_totals=shop_totals)
        return jsonify({
            'shopping_list_html': render_template('shopping_list_table.html', items=updated_items),
            'shop_totals_html': render_template('shop_totals.html', shop_totals=shop_totals)
        })
    
        

    except Exception as e:
        conn.rollback()
        print("❌ Errore nella route add_selected_products:", str(e))
        return "Errore interno", 500






#Mainpage - Calcola il numero dei prodotti in scadenza
@main.route('/expiring_products_count')
def expiring_products_count():

    # Chiama la funzione per contare i prodotti in scadenza
    count = get_number_expiring_products()
    debug_print("expiring_products_count: ", count)

    # Restituisci il conteggio come JSON
    return jsonify({"expiring_products_count": count})

#Mainpage - Calcola il numero dei prodotti esauriti
@main.route('/out_of_stock_count')
def out_of_stock_count():
    print("[DEBUG] Route /out_of_stock_count chiamata")
    # Chiama una funzione per contare i prodotti esauriti
    count = get_out_of_stock_count()
    debug_print("out_of_stock_count: ", count)

    # Restituisci il conteggio come JSON
    return jsonify({"out_of_stock_count": count})

#Mainpage - Calcola il numero dei prodotti con quantity<security_quantity
@main.route('/critical_stock_count')
def critical_stock_count():
    print("[DEBUG] Route /critical_stock_count chiamata")
    count = get_critical_stock_count()
    debug_print("critical_stock_count: ", count)
    return jsonify({"critical_stock_count": count})

#Mainpage - Calcola il numero dei prodotti con quantity<security_quantity
@main.route('/home_critical_stock')
def home_critical_stock():
    print("[DEBUG] Route /home_critical_stock chiamata")
 
    # Recupera i prodotti con scorte critiche
    products = get_critical_stock()
    debug_print("home_out_of_stock_products - Prodotti esauriti: ", products)

    # Se non ci sono prodotti, restituisci un messaggio vuoto
    if not products:
        return jsonify({
            "headers": ["Nome", "Barcode", "Quantita", "Quantita Sicurezza"],
            "records": [],
            "message": "Nessun prodotto esaurito trovato."
        })

    # Restituisci i dati come JSON
    return jsonify({
        "headers": ["Nome", "Barcode", "Quantita", "Quantita Sicurezza"],
        "records": [[p["name"], p["barcode"], p["quantity"], p["security_quantity"]] for p in products]
    })



#Mainpage - Calcola il numero dei prodotti consumati nel mese
@main.route('/monthly_consumed_count')
def monthly_consumed_count():
    print("[DEBUG] Route /monthly_consumed_count chiamata")
    count = get_monthly_consumed_count()
    debug_print("monthly_consumed_count: ", count)
    return jsonify({"monthly_consumed_count": count})



#Mainpage - Conta i prodotti non riconosciuti (unknown)
@main.route('/unknown_products_count')
def unknown_products_count():
    print("[DEBUG] Route /unknown_products_count chiamata")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM unknown_products")
    count = cursor.fetchone()[0]
    conn.close()

    debug_print("unknown_products_count: ", count)
    return jsonify({"unknown_products_count": count})


@main.route('/unknown_products')
def unknown_products():
    print("[DEBUG] Route /unknown_products chiamata")
    rows = get_unknown_products()

    if not rows:
        return jsonify({
            "headers": ["Nome originale", "Nome normalizzato", "Data inserimento", "Prodotto suggerito", "Note"],
            "records": [],
            "message": "Nessun prodotto da confermare."
        })

    return jsonify({
        "headers": ["Nome originale", "Nome normalizzato", "Data inserimento", "Prodotto suggerito", "Note"],
        "records": rows
    })





#Mainpage - Calcola il numero dei prodotti da riordinare
@main.route('/reorder_count')
def reorder_count():
    print("[DEBUG] Route /reorder_count chiamata")
    count = get_reorder_count_from_shopping_list()
    debug_print("reorder_count: ", count)
    return jsonify({"reorder_count": count})

#Mainpage - Calcola il numero dei prodotti consumati nel mese
@main.route('/home_reorder_products')
def home_reorder_products():
    print("[DEBUG] Route /home_reorder_products chiamata")
      
    # Recupera i prodotti da riordinare
       # Verifica se è la settimana di reintegro
    week_number = get_current_week()
    last_week_restock = is_last_week_with_25(week_number)
    items, shop_totals = get_shopping_list_data(week_number, last_week_restock)
    debug_print("home_reorder_producs - Prodotti coda riordinare: ", items)
 
    # Se non ci sono prodotti, restituisci un messaggio vuoto
    if not items:
        return jsonify({
            "headers": ["Nome", "Quantita`", "Negozio", "Motivo"],
            "records": [],
            "message": "Nessun prodotto esaurito trovato."
        })

    # Restituisci i dati come JSON
    return jsonify({
        "headers": ["Nome", "Quantita`", "Negozio", "Motivo"],
        "records": [[p["product_name"], p["quantity_to_buy"], p["shop"], p["reason"]] for p in items]
    })



#Mainpage - Calcola il costo totale dei prodotti da riordinare
@main.route('/reorder_total_cost')
def reorder_total_cost():
    print("[DEBUG] Route /reorder_total_cost chiamata")
    total_cost = get_reorder_total_cost()
    debug_print("reorder_total_cost: ", total_cost)
    return jsonify({"reorder_total_cost": total_cost})

# Budget - Questa route serve per visualizzare e gestire il budget
@main.route('/budget', methods=["GET", "POST"])
def budget():
 
     if request.method == "POST":
        budget = request.form.get("budget", "").strip()
        perc_decade_1 = request.form.get("decade1", "").strip()
        perc_decade_2 = request.form.get("decade2", "").strip()
        perc_decade_3 = request.form.get("decade3", "").strip()
        note = request.form.get("note", "").strip()
        debug_print("budget - Dati ricevuti: ", budget, perc_decade_1, perc_decade_2, perc_decade_3, note)

        if budget:
            upsert_budget(1, budget, perc_decade_1, perc_decade_2, perc_decade_3, note)
            flash("budget salvato con successo!", "success")
        else:
            flash("Inserisci il budget", "error")

     # Sempre recupera la lista completa per la seconda tab
     budget_record = get_budget()

     debug_print("budget_record: ", budget_record)

     return render_template("budget.html", budget_record=budget_record)



# Questa route serve per visualizzare i prodotti avanzati per Node Red
@main.route('/api/shopping_list/current', methods=['GET'])
def get_current_shopping_list():
    current_decade = get_current_decade(datetime.today())
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT product_name, quantity_to_buy, shop
        FROM shopping_list
        WHERE decade_number = ?
    """, (f"D{current_decade}",))
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    debug_print("get_current_shopping_list - Items: ", items)
    
    return jsonify(items)

# Questa route serve per attivare il controllo della coda di acquisto
@main.route('/trigger_queue_check', methods=['POST'])
def trigger_queue_check():
    debug_print("trigger_queue_check - Inizio processo coda acquisto")
    process_shopping_queue()
    return jsonify({"status": "ok"})

# Questa route viene chiamata da Shoppy e serve per aggiornare la lista della spesa prima che sShoppy possa visualizzarla
@main.route("/api/shopping_list/refresh", methods=["POST"])
def api_refresh_shopping_list():
    selected_decade = get_current_decade()

    if is_refresh_needed():
        items, shop_totals = get_shopping_list_data(save_to_db=True, decade=selected_decade)
        set_refresh_needed(False)
        return jsonify({"status": "refreshed", "items_updated": len(items)})
    else:
        return jsonify({"status": "no_refresh_needed"})
    


@main.route('/api/stockhouse/shopping_receipt', methods=['POST'])
def shopping_receipt():
    try:
        raw_data = request.get_json()
        debug_print("shopping_receipt - Dati ricevuti:", raw_data)
        # parsing come prima...
        if isinstance(raw_data, dict) and 'text' in raw_data:
            clean_text = re.sub(r"^```json\n?|```$", "", raw_data['text'].strip())
            data = json.loads(clean_text)
        else:
            data = raw_data

        prodotti = data.get("lista_prodotti", [])
        shop_name = data.get("nome_negozio", "")
        data_scontrino = data.get("data_scontrino", None)
        debug_print("shopping_receipt - Dati ricevuti:", data)

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

            if confidence < 0.95:
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
                prodotto_per_nome = lookup_products_by_name(nome_grezzo)

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

            results.append({
                "nome": nome_grezzo,
                "product_id": product_id,
                "confidence": confidence
            })

        # Alla fine, aggiorna expenses_fact con importo totale e decade_number
        totale = data.get("spesa_totale", None)
        if totale is not None:
            conn = sqlite3.connect(Config.DATABASE_PATH)
            cursor = conn.cursor()
            # usa la nuova versione di upsert_expense con mode='receipt'
            debug_print("Receipt- chiama upsert_expense :", data_scontrino, decade_number, shop_name, totale)
            upsert_expense(cursor, data_scontrino, decade_number, shop_name, totale, mode="receipt")
            conn.commit()
            conn.close()

        return jsonify({
            "status": "ok",
            "matches": results,
            "message": f"{len(results)} prodotti elaborati"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    
@main.route('/unknown/get_all')
def get_all_unknown_products():
    """
    Restituisce tutti i prodotti non riconosciuti scansionati tramite barcode,
    presenti nella tabella unknown_products.
    """
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
            SELECT id, raw_name, shop_name, insert_date, quantita, prezzo_unitario
            FROM unknown_products
            ORDER BY id DESC
        """)
    products = cursor.fetchall()
    return jsonify([dict(row) for row in products])
    
@main.route('/shopping_list/remove_selected', methods=['POST'])
def remove_selected():
    """
    Route per rimuovere i prodotti selezionati dalla lista della spesa.

    - Riceve via POST un JSON con una lista di barcode da rimuovere.
    - Chiama la funzione `remove_from_shopping_lst(barcodes)` per aggiornare il database.
    - Ricarica la lista aggiornata dei prodotti da acquistare, filtrando quelli ancora "within_budget" 
      e appartenenti alla decade corrente, ordinandoli per negozio e nome prodotto.
    - Calcola i totali della spesa per ogni negozio, moltiplicando prezzo per quantità.
    - Renderizza dinamicamente tramite template HTML sia la tabella aggiornata della lista della spesa
      che quella dei totali per negozio.
    - Restituisce un JSON con gli HTML aggiornati per consentire un refresh fluido del frontend senza ricaricare la pagina.
    - Gestisce eventuali errori ritornando un JSON con messaggio di errore e codice 500.
    """

    data = request.get_json()
    barcodes = data.get('barcodes', [])

    if not barcodes:
        return jsonify({"error": "Nessun barcode ricevuto"}), 400

    try:
        remove_from_shopping_lst(barcodes)

        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        current_decade = get_current_decade(datetime.today())

        # Prendi i prodotti filtrati per decade corrente e ordina come in add_selected
        items = cursor.execute("""
            SELECT barcode, product_name, quantity_to_buy, shop, reason, price
            FROM shopping_list
            WHERE within_budget = 1 AND decade_number = ?
            ORDER BY shop, product_name
        """, (current_decade,)).fetchall()

        items = [dict(row) for row in items]

        # Calcola i totali per negozio moltiplicando prezzo * quantità
        shop_totals_raw = cursor.execute("""
            SELECT shop, SUM(price * quantity_to_buy) as total
            FROM shopping_list
            WHERE within_budget = 1 AND decade_number = ?
            GROUP BY shop
            ORDER BY shop                             
        """, (current_decade,)).fetchall()

        shop_totals = {row['shop']: row['total'] for row in shop_totals_raw}

        conn.close()

        shopping_list_html = render_template('shopping_list_table.html', items=items)
        shop_totals_html = render_template('shop_totals.html', shop_totals=shop_totals)

        return jsonify({
            "success": True,
            "shopping_list_html": shopping_list_html,
            "shop_totals_html": shop_totals_html
        })

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@main.route('/import_receipt', methods=['POST'])
def import_receipt():
    """
    Route per ricevere uno scontrino via drag & drop o file input.
    Salva il file nella cartella di lavoro e stampa un debug in console.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'msg': 'Nessun file trovato'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'msg': 'File senza nome'})

    # Salva il file con timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    print(f"[DEBUG] Route /import_receipt chiamata. File salvato: {filepath}")

    return jsonify({'success': True, 'filename': filename})
    
# --- Route di analisi scontrino ---
@main.route('/analyze_receipt', methods=['GET'])
def main_analyze_receipt():
    filename = request.args.get('filename')
    print(f"[DEBUG] Route /analyze_receipt chiamata con file: {filename}")

    if not filename:
        return jsonify({"success": False, "msg": "Nessun file specificato"})

    # Chiama la funzione di analisi
    result_json = analyze_receipt_with_gemini(filename, UPLOAD_FOLDER)

    result_manage = manage_shopping_receipt(result_json)

    # Ritorna il JSON così com'è al frontend
    return jsonify({"success": True, "msg": "Scontrino analizzato", "data": result_manage})


# --- Route di debug per cancellare scontrino ---
@main.route('/delete_receipt', methods=['POST'])
def main_delete_receipt():
    filename = request.json.get('filename') if request.is_json else None
    print(f"[DEBUG] Route /delete_receipt chiamata con file: {filename}")
    return jsonify({"success": True, "msg": "Simulazione cancellazione scontrino"})


# --- Route per finalizzare la lista della spesa ---
@main.route("/shopping_list/finalize", methods=["POST"])
def finalize_shopping_list():
    from threading import Thread

    def background_task():
        debug_print("Thread avviato: riorganizzo la lista secondo i reparti...")
        # qui chiami la funzione z.ai o la logica di riordinamento
        json_data = fetch_shopping_list()
        debug_print("Lista della spesa recuperata:", json_data)
        # ad esempio: reorder_shopping_list()
        debug_print("Thread completato.")

    Thread(target=background_task).start()
    return jsonify({"message": "ok thread avviato"}), 200
