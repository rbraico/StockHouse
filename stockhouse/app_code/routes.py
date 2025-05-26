from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify
from stockhouse.app_code.barcode import lookup_barcode
from stockhouse.app_code.models import add_product_dim, add_transaction_fact, delete_product_from_db,  lookup_products, get_all_products, get_all_shops, get_all_categories, get_all_items, lookup_products_by_name,\
                       lookup_products_by_name_ins_date, update_product_dim, get_product_inventory, get_product_inventory_by_barcode, upsert_inventory, search_unconsumed_products_db, \
                       lookup_category_by_item, update_transaction_fact, update_transaction_fact_consumed, get_products_by_name, get_expiring_products, insert_consumed_fact, \
                       get_number_expiring_products, get_out_of_stock_count, get_critical_stock_count, get_monthly_consumed_count, \
                       get_week_date_range, get_product_by_name_and_dates, get_expiring_products_for_home, get_out_of_stock_products, get_critical_stock, get_monthly_consumed_statistics, \
                       upsert_budget, get_budget, update_inventory_mean_usage_time, get_inventory_advanced, update_inventory_advanced_options, get_unconsumed_products_full_list,  \
                       get_unique_unconsumed_record, clean_old_transactions, update_reorder_frequency
from stockhouse.app_code.models import add_shop, update_shop, delete_shop  
from stockhouse.app_code.models import add_category, get_all_categories, update_category, delete_category, get_all_items, update_item, delete_item
import sqlite3
import hashlib
from datetime import datetime, timedelta
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
    get_budget_info,
    get_total_spesa_corrente,
    get_reorder_count_from_shopping_list,
    get_reorder_total_cost,
    get_suggested_products,
    generate_monthly_shopping_list,
    get_current_decade,
    format_decade_label)

main = Blueprint('main', __name__)


@main.route('/')
def homepage():
    decade_number = get_current_decade()
    current_decade_label = format_decade_label(decade_number)
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
    
    
    debug_print("⚡ Routes: Funzione index() chiamata!")  # 🔍 Controllo se la funzione viene eseguita
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
            add_product_dim(barcode, name, brand, shop, category, item, image_browser_path)

        # Ottiene ID del prodotto
        if product_key is None:
           prodotto_esistente=lookup_products_by_name(name)
           product_key = prodotto_esistente["id"]    
 
        # Salva la tranasazione
        add_transaction_fact(product_key, barcode, price, quantity, ins_date, consume_date, expiry_date, status)
        flash("Prodotto aggiunto o aggiornato!", "success")

        # Prepara un dizionario con i dati del prodotto appena inserito
        new_product = {
            "barcode": barcode,
            "name": name,
            "brand": brand,
            "shop": shop,
            "price": price,
            "quantity": quantity,
            "category": category,
            "item": item,
            "expiry_date": expiry_date 
            }

    # 💡 Se la richiesta è GET, semplicemente carichiamo la pagina
    products      = get_all_products()
    shops         = get_all_shops()
    #debug_print("ALL SHOPS: ", shops)
    categories    = get_all_categories()
    items = get_all_items()

    return render_template("index.html",
                        products=products,
                        shops=shops,
                        categories=categories,
                        items=items,
                        new_product=new_product)

@main.route('/delete_product/<int:id>')
def delete_product(id):
    debug_print("delete_product: " , id)

    delete_product_from_db(id)

    flash("prodotto eliminato.", "success")

    # Redirect alla lista dei prodotti
    return redirect(url_for('main.index') + '#manage')

# ✅ Nuova route per la lista prodotti nel magazzino
@main.route('/inventory')
def list_inventory():

    clean_old_transactions                  # 🧽 Step 1: pulizia
    update_inventory_mean_usage_time()           # 🧠 Step 2: calcolo mean_usage_time
    update_reorder_frequency()              # 🔄 Step 3: calcolo reorder_frequency
    products = get_product_inventory()      # 🏭 Step 4 - Seleziona i records per l'inventario

    #debug_print ("Show_Product in inventory: ", products)

    return render_template("inventory.html", products=products)

# Questa procedura viene chiamata dal metodo POST dopo aver cliccato sul pulsante Modifica Parametri di Magazzino
# Per inserire oppure modificare un record esistente nella tabella product_dim
@main.route('/inventory/update_inline', methods=['POST'])
def update_inventory_inline():
    data = request.get_json()
    barcode = data.get('barcode')
    allowed_fields = [
        'min_quantity', 'max_quantity', 'security_quantity',
        'reorder_point', 'mean_usage_time', 'reorder_frequency', 'user_override'
    ]
    updates = []
    values = []
    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            values.append(data[field])
    if not updates:
        return jsonify(success=False, error="Nessun campo da aggiornare")
    values.append(barcode)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE inventory SET {', '.join(updates)} WHERE barcode = ?", values)
    conn.commit()
    conn.close()
    return jsonify(success=True)


@main.route("/edit/<name>/<ins_date>", methods=["GET", "POST"])
#La procedura viene chiamata da Prodotti--> Modifica/Rimuovi Prodotta al momento del click sul pulsaante Modifica
# Il metodo GET serve a riempire il form con i dati relativi il prodotto selezionato
# Il metodo POST serve per attivare la modifica nel Database
def edit_product(name, ins_date):
    # Recupera i dettagli del prodotto dal database per il form di modifica
    debug_print("edith_product: ", name, ins_date)
    debug_print("requested method: ", request.method)

    product    = lookup_products_by_name_ins_date(name,ins_date)
    id = product["id"]
    shop_list  = get_all_shops()
    items = get_all_items()
    debug_print("requested method: ", product)
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
        debug_print ("update_product: ", barcode, name, brand, shop, item, ins_date)
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

    if quantity > 1:
        new_quantity = quantity - 1
        new_status = "in stock"
        consume_date = None 
    else:
        new_quantity = 0
        new_status = "out of stock"
        consume_date = datetime.now().strftime("%Y-%m-%d")

    debug_print("Route 1: /consumed_product/",id, new_quantity, ins_date, expiry_date, consume_date, new_status)    

    update_transaction_fact_consumed(id, new_quantity, ins_date, expiry_date, consume_date, new_status)

    #Registra il consumo in consume_fact
    insert_consumed_fact (product_key, barcode, ins_date, expiry_date)
    
    return jsonify(success=True, quantita=new_quantity, status=new_status, consumo=consume_date)

@main.route('/consumed/get_records', methods=["GET"])
def get_records():
    # Ottieni i parametri dalla richiesta
    name = request.args.get('name')  # Nome del prodotto
    barcode = request.args.get('barcode') # Barcode del prodotto
    ins_date = request.args.get('ins_date')  # Data di inserimento
    expiry_date = request.args.get('expiry_date')  # Data di scadenza (può essere NULL)

    # Debugging: stampa i parametri ricevuti
    debug_print("get_records - name: ", name)
    debug_print("get_records - barcode: ", barcode)
    debug_print("get_records - Data di inserimento: ", ins_date)
    debug_print("get_records - Data di scadenza: ", expiry_date)

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

#
@main.route('/home_expiring_products', methods=['GET'])
def home_expiring_products():
    # Ottieni il parametro "months" dalla query string (default: 1 mese)
    months = int(request.args.get('months', 1))
    debug_print(f"home_expiring_products - Filtro mesi: {months}")

    # Recupera i prodotti in scadenza entro il numero di mesi specificato
    products = get_expiring_products_for_home(months)
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




# Questa route serve per visualizzare la lista della spesa
@main.route('/shopping_list')
def shopping_list():
    # Legge il numero della decade dal parametro GET
    decade_param = request.args.get('decade')
    debug_print("shopping_list decade_param: ", decade_param)

    # Se non specificata, usa la decade corrente
    selected_decade = decade_param or get_current_decade()
    debug_print("Decade selezionata: ", selected_decade)

    # Verifica se la lista mensile è già stata generata
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    current_month = datetime.today().strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) FROM shopping_list WHERE strftime('%Y-%m', insert_date) = ?", (current_month,))
    already_generated = cursor.fetchone()[0] > 0
    conn.close()

    debug_print("shopping_list - Lista mensile già generata: ", already_generated)
    if not already_generated:
        debug_print("Lista mensile non trovata. Generazione in corso...")
        generate_monthly_shopping_list()
    else:
        debug_print("Lista mensile già generata.")

    # Recupera i dati della lista spesa per la decade selezionata
    debug_print("Recupero dati della lista spesa per la decade selezionata: ", selected_decade)
    items, shop_totals = get_shopping_list_data(save_to_db=True, decade=selected_decade)

    # Recupera i prodotti suggeriti
    suggested_items = get_suggested_products()

    # Dropdown delle decadi (fisso)
    decades = [
        ("D1", "1ª Decade (1-10)"),
        ("D2", "2ª Decade (11-20)"),
        ("D3", "3ª Decade (21-31)")
    ]

    # Recupera budget, spesa effettuata, residuo
    budget, budget_date = get_budget_info()
    spesa_corrente = get_total_spesa_corrente()
    budget_residuo = round(budget - spesa_corrente, 2)

    return render_template(
        'shopping_list.html',
        items=items,
        shop_totals=shop_totals,
        decades=decades,
        selected_decade=selected_decade,
        suggested_items=suggested_items,
        budget=budget,
        spesa_corrente=spesa_corrente,
        budget_residuo=budget_residuo
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
            try:
                week_number = get_current_week()
                cursor.execute("""
                    INSERT INTO shopping_list (barcode, product_name, quantity_to_buy, shop, reason, price, week_number) )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (barcode, row["name"], 1, row["shop"], "Sotto scorta", row["price"], week_number))
                 
            except Exception as insert_error:
                debug_print("❌ Errore durante INSERT:", str(insert_error))

        conn.commit()
          
        # Ricarica la nuova lista 
        cursor.execute("""
            SELECT barcode, product_name, quantity_to_buy, shop, reason, price
            FROM shopping_list
            ORDER BY shop, product_name
        """)

        updated_items = cursor.fetchall()
        conn.close()
  
        return render_template('shopping_list_table.html', items=updated_items)

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

#Mainpage - Calcola il numero dei prodotti consumati nel mese
@main.route('/home_consume_statistics')
def home_consume_statistics():
    print("[DEBUG] Route /home_consume_statistics chiamata")
      
    # Recupera i prodotti per le statistiche sui consumi
    products = get_monthly_consumed_statistics()
    debug_print("home_consume_statistics - Prodotti consumati: ", products)
 
    # Se non ci sono prodotti, restituisci un messaggio vuoto
    if not products:
        return jsonify({
            "headers": ["Nome", "Inserimento", "Consumato", "Scadenza"],
            "records": [],
            "message": "Nessun prodotto esaurito trovato."
        })

    # Restituisci i dati come JSON
    return jsonify({
        "headers": ["Nome", "Inserimento", "Consumato", "Scadenza"],
        "records": [[p["name"], p["ins_date"], p["consume_date"], p["expiry_date"]] for p in products]
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

@main.route('/budget', methods=["GET", "POST"])
def budget():
 
     if request.method == "POST":
        budget = request.form.get("budget", "").strip()
        note = request.form.get("note", "").strip()
        if budget:
            upsert_budget(1, budget, note)
            flash("budget salvato con successo!", "success")
        else:
            flash("Inserisci il budget", "error")

     # Sempre recupera la lista completa per la seconda tab
     budget_record = get_budget()

     debug_print("budget_record: ", budget_record)

     return render_template("budget.html", budget_record=budget_record)


# Questa route serve per visualizzare i parametri avanzati di inventory
#@main.route('/inventory/advanced/data')
#def inventory_advanced_data():
#    advanced_inventory = get_inventory_advanced()
#    debug_print("inventory_advanced_data - Prodotti avanzati: ", advanced_inventory)
#    return jsonify(advanced_inventory)


# Funzione per calcolare il livello di priorità in base alla stagione
@main.route('/inventory/advanced')
def inventory_advanced():
    # Ottieni i prodotti avanzati tramite la funzione del modello
    advanced_inventory = get_inventory_advanced()

    debug_print("inventory_advanced - Prodotti avanzati: ", advanced_inventory)

    # Renderizza la pagina e passa i prodotti alla template
    return render_template("inventory.html", products=advanced_inventory)

# Questa route serve per visualizzare i prodotti avanzati
@main.route('/inventory/advanced/update', methods=['POST'])
def update_expense():
    barcode = request.form.get('barcode')
    product_type = request.form.get('product_type')
    seasons = request.form.get('seasons')

    debug_print("update_expense: ", barcode, product_type, seasons)

    if barcode:
        update_inventory_advanced_options(barcode, product_type, seasons)
        debug_print("Aggiornamento riuscito")
        return jsonify({'success': True})
    else:
        debug_print("Errore: barcode mancante")
        return jsonify({'success': False, 'error': 'Barcode mancante'})


@main.route("/products/advanced", methods=["GET"])
def products_advanced():
    debug_print("get_products_advanced - Chiamata API ricevuta")

    inventory_advanced = get_inventory_advanced()
   
    #debug_print("get_expense_products - Prodotti: ", inventory_advanced)

    return jsonify({"found": bool(inventory_advanced), "products": inventory_advanced})

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