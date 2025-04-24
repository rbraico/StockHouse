from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify
from stockhouse.app_code.barcode import lookup_barcode
from stockhouse.app_code.models import add_product_dim, add_transaction_fact, delete_product_from_db,  lookup_products, get_all_products, get_all_shops, get_all_categories, get_all_items, lookup_products_by_name,\
                       lookup_products_by_name_ins_date, update_product_dim, get_product_inventory, get_product_inventory_by_barcode, upsert_inventory, search_unconsumed_products_db, \
                       lookup_category_by_item, update_transaction_fact, update_transaction_fact_consumed, get_products_by_name
from stockhouse.app_code.models import add_shop, update_shop, delete_shop  # Assicurati che queste funzioni esistano in models.py
from stockhouse.app_code.models import add_category, get_all_categories, update_category, delete_category, add_item, get_all_items, update_item, delete_item
import sqlite3
import hashlib
import datetime
from config import Config  # usa il path corretto se è diverso
from flask import send_from_directory
import os
from config import Config


main = Blueprint('main', __name__)

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

#Chiamata dallo script in index.html
@main.route("/lookup", methods=["GET"])
def lookup():
    barcode = request.args.get("barcode")
    name = request.args.get("name")

    # 1️⃣ Se c'è un barcode, proviamo a cercare localmente
    if barcode:
        prodotto_esistente = lookup_products(barcode=barcode)
        if prodotto_esistente["found"]:
            print("lookup barcode: ", prodotto_esistente)
            return jsonify(prodotto_esistente)

    # 2️⃣ Se non trovato o non c'è barcode, ma c'è il nome, cerca localmente per nome
    if name:
        prodotto_per_nome = lookup_products_by_name(name)
        if prodotto_per_nome["found"]:
            print("lookup per nome: ", prodotto_per_nome)
            return jsonify(prodotto_per_nome)


    # 3️⃣ Se c'è barcode e non abbiamo ancora trovato nulla, cerca online
    if barcode:
       data = lookup_barcode(barcode)
       print("lookup online: ", data)
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
@main.route('/', methods=["GET", "POST"])
def index():
    print("⚡ Routes: Funzione index() chiamata!")  # 🔍 Controllo se la funzione viene eseguita
    print(f" Routes: Metodo richiesta: {request.method}")  # 🔍 Controllo se arriva POST o GET

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

        print("index -> POST", barcode,name,brand,shop,price,quantity,category,item,expiry_date )

        # Ottieni la data odierna e formatta come yyyy-mm-dd
        ins_date     = datetime.datetime.now().strftime('%Y-%m-%d')
        consume_date = None
        status       = 'in stock'
        product_key  = None
        
        # Verifica se il prodotto e` presente in product_dim usando name, poiche barcode puo anche essere null
        prodotto_esistente = lookup_products_by_name(name)

        print(f"Risultato lookup DB: {prodotto_esistente}")

        if prodotto_esistente and prodotto_esistente["found"]:
            product_key = prodotto_esistente["id"]  
            name        = prodotto_esistente["name"]
            brand       = prodotto_esistente["brand"]
            shop        = prodotto_esistente["shop"]
            category    = prodotto_esistente["category"]
            item        = prodotto_esistente["item"]
            image       = prodotto_esistente["image"]
            print("index -> POST 2", barcode,name,brand,shop,price,quantity,category,item )
        else:
            # Il prodotto non e` presente in product_dim, cerca online con il barcode
            data = lookup_barcode(barcode)
            print("index -> POST 3", barcode,name,brand,shop,price,quantity,category,item )
            if "error" not in data:
                name = data["name"]
                brand = data["brand"]
                quantity = quantity if quantity else data["quantity"]  # ✅ Mantiene il valore inserito, a meno che non sia vuoto
                image = data.get("image", None)
                print("index -> POST 4", barcode,name,brand,shop,price,quantity,category,item )

            # INSERT in product_dim anche se il barcode e` null oppure non e`stato trovato online
            print ("index -> add_product_dim: ", barcode, name, brand, shop, category, item, image)      
            result = lookup_category_by_item(item)

            # Associare il risultato alla variabile 'category' se trovato
            if result["found"]:
                category = result["category"]
                print(f"La categoria dell'item '{item}' è: {category}")
            else:
                print(f"Item '{item}' non trovato.")

            # INSERT in product_dim anche se il barcode e` null oppure non e`stato trovato online
            print ("index -> add_product_dim: ", barcode, name, brand, shop, category, item, image)      
        
            # Prepara l'immagine per il DB         
            if barcode:
                # Ottieni l'URL base per le immagini
                image_url = Config.get_image_url()
                # Costruisci il nome del file immagine
                image_filename = f"{barcode}.jpg"
                # Percorso assoluto dell'immagine sul filesystem
                image_path = os.path.join(Config.get_image_folder(), image_filename)

                print(f"[DEBUG] image_url: {image_url}")
                print(f"[DEBUG] image_filename: {image_filename}")
                print(f"[DEBUG] image_path: {image_path}")

                if os.path.exists(image_path):
                    # Percorso per il browser (Home Assistant espone /config/www come /local)
                    image_browser_path = f"{image_url}/{image_filename}"
                    print(f"[DEBUG] image_browser_path: {image_browser_path}")
                else:
                    # Se l'immagine non esiste, nessun percorso per il browser
                    image_browser_path = None
                    print("[WARNING] Immagine non trovata.")
            else:
                # Nessun barcode, nessun percorso immagine
                image_browser_path = None
                print("[INFO] Nessun barcode fornito.")

            print("index -> add_product_dim: ", image_path)

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

    # 💡 Se la richiesta è GET, semplicemente carichiamo la pagina
    products      = get_all_products()
    shops         = get_all_shops()
    #print("ALL SHOPS: ", shops)
    categories    = get_all_categories()
    items = get_all_items()

    return render_template("index.html", products=products, shops=shops, categories=categories, items=items)

@main.route('/delete_product/<int:id>')
def delete_product(id):
    print("delete_product: " , id)

    delete_product_from_db(id)

    flash("prodotto eliminato.", "success")

    # Redirect alla lista dei prodotti
    return redirect(url_for('main.index') + '#manage')

# ✅ Nuova route per la lista prodotti nel magazzino
@main.route('/inventory')
def list_inventory():
    products = get_product_inventory()
    print ("Show_Product in inventory: ", products)

    return render_template("inventory.html", products=products)


@main.route("/inventory/<barcode>", methods=["GET"])
# Questa procedura apre e riempie il form per eseguire modifiche esclusivamente sui parametri di magazzino
def edit_inventory(barcode):
    # Recupera i dettagli del prodotto dal database
    product = get_product_inventory_by_barcode(barcode)
    print("edith_inventory: ", product)
    return render_template("edit_inventory.html", product=product)


@main.route("/update_inventory", methods=["POST"])
# Questa procedura viene chamtaa dal metodo POST dopo aver cliccato sul pulsante Modifica Parametri di Magazzino
# Per inserire oppure modificare un record esistente nella tabella inventory
def update_inventory():
    print("update_inventory Request Form Data: ", request.form)

    data = {
        "barcode": request.form["barcode"],
        "min_quantity": int(request.form["min_quantity"]),
        "max_quantity": int(request.form["max_quantity"]),
        "security_quantity": int(request.form["security_quantity"]),
        "reorder_point": int(request.form["reorder_point"]),
        "mean_usage_time": int(request.form["mean_usage_time"]),
        "reorder_frequency": request.form["reorder_frequency"],
        "user_override": int(request.form["user_override"])
    }
    print("update_inventory: ", data)
    upsert_inventory(data)

    flash("inventory aggiornato con successo!")
    return redirect(url_for("main.edit_inventory", barcode=data["barcode"]))


@main.route("/edit/<name>/<ins_date>", methods=["GET", "POST"])
#La procedura viene chiamata da Prodotti--> Modifica/Rimuovi Prodotta al momento del click sul pulsaante Modifica
# Il metodo GET serve a riempire il form con i dati relativi il prodotto selezionato
# Il metodo POST serve per attivare la modifica nel Database
def edit_product(name, ins_date):
    # Recupera i dettagli del prodotto dal database per il form di modifica
    print("edith_product: ", name, ins_date)
    print("requested method: ", request.method)

    product    = lookup_products_by_name_ins_date(name,ins_date)
    id = product["id"]
    shop_list  = get_all_shops()
    items = get_all_items()
    print("requested method: ", product)
    print("edit product intero record: ", product)

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
        print ("update_product: ", barcode, name, brand, shop, item, ins_date)
        category = lookup_category_by_item(item)
        update_product_dim(id, name, brand, shop, category, item)
        update_transaction_fact(id, price, quantity,  expiry_date, ins_date)
        flash("Prodotto aggiornato con successo!", "success")
        return redirect(url_for('main.index') + '#manage')  # Torna alla lista dei prodotti dopo il salvataggio
    

    return render_template("edit_product.html", product=product, shop_list=shop_list, items=items)


@main.route('/consumed/search')
def search_unconsumed_products():
    query = request.args.get('q', '')
    print("Route - unconsumed products1: ", query)
    
    # Chiamata alla funzione nel modello
    results = search_unconsumed_products_db(query)
    
    print("Route - unconsumed products2: ", results)
    return jsonify(results)


@main.route('/consumed_product', methods=['GET', 'POST'])
def consumed_product():
    id = request.args.get('id')
    ins_date = request.args.get('ins_date')
    expiry_date = request.args.get('expiry_date')
    quantity = int(request.args.get('quantity'))

    print("Route: /consumed_product/", id, quantity, ins_date, expiry_date)

    if quantity > 1:
        new_quantity = quantity - 1
        new_status = "in stock"
        consume_date = None 
    else:
        new_quantity = 0
        new_status = "out of stock"
        consume_date = datetime.datetime.now().strftime("%Y-%m-%d")

    print("Route 1: /consumed_product/",id, new_quantity, ins_date, expiry_date, consume_date, new_status)    

    update_transaction_fact_consumed(id, new_quantity, ins_date, expiry_date, consume_date, new_status)

    return jsonify(success=True, quantita=new_quantity, status=new_status, consumo=consume_date)


@main.route('/consumed/get_records', methods=["GET"])
def get_records():

 
    name = request.args.get('nome')
    print("get_records: ",name)
    if not name:
        return jsonify({"error": "Parametro 'nome' mancante"}), 400

    prodotto = get_products_by_name(name)
    print("get_records: ", prodotto)
    if not prodotto:
        return jsonify({"error": f"Prodotto '{name}' non trovato"}), 404

    return jsonify({"success": True, "data": prodotto})



@main.route('/configuration', methods=["GET", "POST"])
def configuration():
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

    return render_template("configuration.html", shop_list=shop_list, last_shop=last_shop)


@main.route('/delete_shop/<int:shop_id>')
def delete_shop(shop_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shop_list WHERE id = ?", (shop_id,))
    conn.commit()
    conn.close()
    flash("Negozio eliminato.", "success")
    return redirect(url_for('main.configuration'))

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
        return redirect(url_for('main.configuration'))
    
    c.execute("SELECT id, name, note FROM shop_list WHERE id = ?", (shop_id,))
    shop = c.fetchone()
    conn.close()
    if shop:
        return render_template('edit_shop.html', shop=shop)
    else:
        flash('❌ Negozio non trovato.', 'danger')
        return redirect(url_for('main.configuration'))

@main.route('/delete_shop/<int:shop_id>', methods=['POST'])
def delete_shop_route(shop_id):
    delete_shop(shop_id)
    flash('🗑️ Negozio eliminato con successo!', 'success')
    return redirect(url_for('main.configuration'))

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
    print("edit_item: ", request.method)

    if request.method == 'POST':
        print("edit_item: ", request.form['name'], request.form['note'], request.form['category'])
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
    print("item: ", item)
    conn.close()
    return render_template('edit_item.html', categories=categories, item=item)


@main.route('/delete_item/<int:item_id>', methods=['POST'])
def delete_item_route(item_id):  # 🔁 Cambia nome alla funzione route per evitare conflitti
    delete_item(item_id)  # ✅ Questa è la funzione del modello
    flash('🗑️ Sub Categoria eliminata con successo!', 'success')
    return redirect(url_for('main.items'))