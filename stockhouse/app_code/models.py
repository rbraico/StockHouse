import sqlite3
from datetime import datetime, timedelta
from config import Config  # usa il path corretto se è diverso
from stockhouse.utils import debug_print
from calendar import monthrange

def init_db():
 
    conn = sqlite3.connect(Config.DATABASE_PATH)
  
    # ✅ CREA PRODUCT_DIM ####################################
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS product_dim (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT ,
            name TEXT,
            brand TEXT,
            shop TEXT,
            category TEXT,
            item TEXT,  
            image TEXT  
        )
    """)
    conn.commit()

    # ✅ CREA TABELLA NEGOZI #################################
    c.execute("""
        CREATE TABLE IF NOT EXISTS shop_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            note TEXT,
            UNIQUE (name, note)  
        )
    """)
    conn.commit()

    # ✅ CREA TABELLA CATEGORIE ##############################
    c.execute('''
        CREATE TABLE IF NOT EXISTS category_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            note TEXT
        )
    ''')
    conn.commit()

    # ✅ CREA TABELLA dei nomi dei prodotti ###########################
    c.execute('''
        CREATE TABLE IF NOT EXISTS item_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            note TEXT,
            category_id INTEGER,
            FOREIGN KEY (category_id) REFERENCES category_list(id)
        )
    ''')




    conn.commit()   


   # ✅ CREA TABELLA  CONSUMED (fatti) #####################
    c.execute("""
         CREATE TABLE IF NOT EXISTS consumed_fact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key INTEGER,
            barcode TEXT,
            ins_date TEXT,
            consume_date TEXT,
            expiry_date TEXT,
            FOREIGN KEY(product_key) REFERENCES product_dim(id)
        )
    """)

    conn.commit()

    # ✅ CREA TABELLA INVENTORY che contiene i parametri di magazzino
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key INTEGER,  
            barcode TEXT,
            min_quantity INTEGER,
            max_quantity INTEGER,
            security_quantity INTEGER,
            reorder_point INTEGER,
            mean_usage_time INTEGER,
            reorder_frequency TEXT,
            user_override INTEGER DEFAULT 1,
            FOREIGN KEY(product_key) REFERENCES product_dim(id)
        )
    """)
    conn.commit()
 
    conn.close()

import sqlite3

# Esegue Lookup nel database, tabella prodotti
def lookup_products(barcode):
    conn = sqlite3.connect(Config.DATABASE_PATH)  # Sostituisci con il nome corretto del tuo DB
    cursor = conn.cursor()
 
    cursor.execute("""
        SELECT 
            p.id, 
            p.name, 
            p.brand, 
            p.shop, 
            tf.price, 
            tf.quantity, 
            c.name AS category, 
            p.item, 
            p.image
        FROM product_dim p
        LEFT JOIN item_list i ON p.item = i.name
        LEFT JOIN category_list c ON i.category_id = c.id
        LEFT JOIN (
            SELECT tf1.product_key, tf1.price, tf1.quantity
            FROM transaction_fact tf1
            JOIN (
                SELECT product_key, MAX(ins_date) AS max_date
                FROM transaction_fact
                GROUP BY product_key
            ) tf2 ON tf1.product_key = tf2.product_key AND tf1.ins_date = tf2.max_date
        ) tf ON p.id = tf.product_key
        WHERE p.barcode = ?
    """, (barcode,))

    prodotto = cursor.fetchone()  # Restituisce una tupla se esiste, altrimenti None
    debug_print("lookup_products: ", prodotto)
    
    conn.close()
    
    if prodotto:
        return {
            "found": True,
            "id": prodotto[0],
            "name": prodotto[1],
            "brand": prodotto[2],
            "shop": prodotto[3],
            "price": prodotto[4],
            "quantity": prodotto[5],
            "category": prodotto[6],
            "item": prodotto[7],
            "image": prodotto[8]
        }
    else:
        return {"found": False}

# Esegue Lookup in product_dim per ottenere la chiave. Il barcode puo anche essere null. Name mai
def lookup_products_by_name(name):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            p.id, 
            p.name, 
            p.brand, 
            p.shop, 
            tf.price, 
            tf.quantity, 
            c.name AS category, 
            p.item, 
            p.image
        FROM product_dim p
        LEFT JOIN item_list i ON p.item = i.name
        LEFT JOIN category_list c ON i.category_id = c.id
        LEFT JOIN (
            SELECT tf1.product_key, tf1.price, tf1.quantity
            FROM transaction_fact tf1
            JOIN (
                SELECT product_key, MAX(ins_date) AS max_date
                FROM transaction_fact
                GROUP BY product_key
            ) tf2 ON tf1.product_key = tf2.product_key AND tf1.ins_date = tf2.max_date
        ) tf ON p.id = tf.product_key
        WHERE p.name = ?
    """, (name,))

    prodotto = cursor.fetchone()
    conn.close()
  
    debug_print ("lookup_products_by_name: ", prodotto)

    if prodotto:
        return {
            "found": True,
            "id": prodotto[0],
            "name": prodotto[1],
            "brand": prodotto[2],
            "shop": prodotto[3],
            "price": prodotto[4],
            "quantity": prodotto[5],
            "category": prodotto[6],
            "item": prodotto[7],
            "image": prodotto[8]
        }
    else:
        return {"found": False}
    
def lookup_products_by_name_ins_date(name, ins_date):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            p.id, 
            tf.barcode,
            p.name, 
            p.brand, 
            p.shop, 
            tf.price, 
            tf.quantity, 
            c.name AS category, 
            p.item, 
            tf.ins_date,
            tf.expiry_date,
            p.image
        FROM product_dim p
        LEFT JOIN item_list i ON p.item = i.name
        LEFT JOIN category_list c ON i.category_id = c.id
        LEFT JOIN (
            SELECT tf1.product_key, tf1.barcode, tf1.price, tf1.quantity, tf1.ins_date, tf1.expiry_date
            FROM transaction_fact tf1
            JOIN (
                SELECT product_key, MAX(ins_date) AS max_date
                FROM transaction_fact
                GROUP BY product_key
            ) tf2 ON tf1.product_key = tf2.product_key AND tf1.ins_date = tf2.max_date
        ) tf ON p.id = tf.product_key
        WHERE p.name = ? AND tf.ins_date = ?
    """, (name, ins_date))

    prodotto = cursor.fetchone()
    conn.close()
  
    debug_print ("lookup_products_by_name: ", prodotto)

    if prodotto:
        return {
            "found": True,
            "id": prodotto[0],
            "barcode": prodotto[1],
            "name": prodotto[2],
            "brand": prodotto[3],
            "shop": prodotto[4],
            "price": prodotto[5],
            "quantity": prodotto[6],
            "category": prodotto[7],
            "item": prodotto[8],
            "ins_date": prodotto[9],
            "expiry_date": prodotto[10],
            "image": prodotto[11]
        }
    else:
        return {"found": False}

def lookup_category_by_item(item_name):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.name
        FROM item_list i
        LEFT JOIN category_list c ON i.category_id = c.id
        WHERE i.name = ?
    """, (item_name,))
    
    category = cursor.fetchone()
    conn.close()

    if category:
        return {
            "found": True,
            "category": category[0]
        }
    else:
        return {"found": False}

def add_product_dim(barcode, name, brand, shop, category, item, image):

    debug_print(f"Risultato: Barcode={barcode}, Name={name}, Brand={brand}, Shop={shop}, Category={category}, Item={item}")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO product_dim (barcode, name, brand, shop, category, item, image)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (barcode, name, brand, shop, category, item, image
          ))
    conn.commit()
    conn.close()


def update_product_dim(id, name, brand, shop, category, item):

    category = category.get("category")
    debug_print ("update_product_dim: ", id, name, brand, shop, category, item)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE product_dim
        SET name = ?, brand = ?, shop = ?, category = ?, item = ?
        WHERE id = ?
    """, (name, brand, shop, category, item, id))
    conn.commit()
    conn.close()

def delete_product_from_db(id):
    debug_print("delete_product: ", id)
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Query per eliminare il prodotto con il dato md5
    cur.execute("DELETE FROM transaction_fact WHERE id = ?", (id,))

    # Commit e chiusura della connessione
    conn.commit()
    conn.close()



def get_all_products():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    
    c.execute("""
        SELECT 
            trs.id, 
            dim.barcode,
            dim.name, 
            dim.brand, 
            dim.shop, 
            trs.price, 
            cat.name AS category, 
            itl.name AS item,
            trs.quantity,
            trs.ins_date, 
            trs.consume_date, 
            trs.expiry_date, 
            trs.status,  
            dim.image
        FROM transaction_fact trs
        INNER JOIN product_dim dim ON dim.id = trs.product_key
        LEFT JOIN item_list itl ON dim.item = itl.name
        LEFT JOIN category_list cat ON itl.category_id = cat.id
        WHERE trs.consume_date IS NULL
        ORDER BY dim.name
    """)

    rows = c.fetchall()

    conn.close()

    # Convertiamo le tuple in una lista di dizionari
    products = [
        {
            "id":row[0],
            "barcode": row[1],
            "name": row[2],
            "brand": row[3],
            "shop": row[4],
            "price": row[5],
            "category": row[6],
            "item": row[7],
            "quantity": row[8],
            "ins_date": row[9],
            "consume_date": row[10],
            "expiry_date": row[11],
            "status": row[12],
            "image": row[13]
        }
        for row in rows
    ]

    return products  # 🔥 Ora restituisce una lista di dizionari!

def get_products_by_name(name):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            p.id, 
            p.name, 
            p.barcode,
            p.brand, 
            p.shop, 
            tf.price, 
            tf.quantity, 
            tf.ins_date,
            tf.expiry_date,
            tf.consume_date,
            tf.status,
            c.name AS category, 
            p.item, 
            p.image
        FROM product_dim p
        LEFT JOIN item_list i ON p.item = i.name
        LEFT JOIN category_list c ON i.category_id = c.id
        LEFT JOIN (
            SELECT tf1.product_key, tf1.price, tf1.quantity, tf1.ins_date, tf1.expiry_date, tf1.consume_date, tf1.status
            FROM transaction_fact tf1
            JOIN (
                SELECT product_key, MAX(ins_date) AS max_date
                FROM transaction_fact
                GROUP BY product_key
            ) tf2 ON tf1.product_key = tf2.product_key AND tf1.ins_date = tf2.max_date
        ) tf ON p.id = tf.product_key
        WHERE p.name = ?
    """, (name,))

    prodotti = cursor.fetchall()  # Usa fetchall per ottenere più prodotti
    conn.close()

    debug_print("lookup_products_by_name: ", prodotti)

    if prodotti:
        result = []
        for p in prodotti:
            result.append({
                "found": True,
                "id": p[0],
                "name": p[1],
                "barcode": p[2],
                "brand": p[3],
                "shop": p[4],
                "price": p[5],
                "quantity": p[6],
                "inserito": p[7],
                "scadenza": p[8],
                "consumo": p[9],
                "stato": p[10],
                "category": p[11],
                "item": p[12],
                "image": p[13]
            })
        return result  # Restituisci una lista di prodotti
    else:
        return []  # Nessun risultato

def get_product_by_name_and_dates(name, ins_date, expiry_date=None):
    """
    Recupera un prodotto dal database utilizzando nome, data di inserimento e (opzionalmente) data di scadenza.
    """
    debug_print("get_product_by_name_and_dates - Nome: ", name)
    debug_print("get_product_by_name_and_dates - Data di inserimento: ", ins_date)
    debug_print("get_product_by_name_and_dates - Data di scadenza: ", expiry_date)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    if expiry_date:  # Se la data di scadenza è fornita
        query = """
            SELECT tf.id, pd.name, tf.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status
            FROM transaction_fact tf
            JOIN product_dim pd ON tf.product_key = pd.id
            WHERE pd.name = ? AND tf.ins_date = ? AND tf.expiry_date = ?
        """
        params = (name, ins_date, expiry_date)
    else:  # Se la data di scadenza non è fornita
        query = """
            SELECT tf.id, pd.name, tf.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status
            FROM transaction_fact tf
            JOIN product_dim pd ON tf.product_key = pd.id
            WHERE pd.name = ? AND tf.ins_date = ? AND tf.expiry_date IS NULL
        """
        params = (name, ins_date)

    debug_print("get_product_by_name_and_dates - Query: ", query)
    debug_print("get_product_by_name_and_dates - Parametri: ", params)

    cur.execute(query, params)
    records = cur.fetchall()
    conn.close()

    debug_print("get_product_by_name_and_dates - Risultati: ", records)

    # Formatta i risultati in un dizionario
    return [{
        "id": row[0],
        "name": row[1],
        "barcode": row[2],
        "quantity": row[3],
        "inserito": row[4],
        "scadenza": row[5],
        "consumo": row[6],
        "stato": row[7]
    } for row in records]

def search_unconsumed_products_db(query):
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Prepara il parametro per la ricerca LIKE
    query_param = f"%{query.lower()}%"  # La query deve essere case insensitive

    if query.isdigit():  # Se la query è un barcode
        cur.execute(""" 
            SELECT DISTINCT pd.id, pd.name, pd.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status 
            FROM product_dim pd
            JOIN transaction_fact tf ON pd.id = tf.product_key
            WHERE pd.barcode LIKE ? AND tf.consume_date IS NULL
            GROUP BY pd.barcode, ins_date
        """, (query_param,))
    else:  # Se la query è un nome prodotto
        cur.execute("""
            SELECT DISTINCT pd.id, pd.name, pd.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status
            FROM product_dim pd
            JOIN transaction_fact tf ON pd.id = tf.product_key
            WHERE LOWER(pd.name) LIKE ? AND tf.consume_date IS NULL
            GROUP BY pd.name, ins_date
        """, (query_param,))

    # Recupera i risultati
    results = cur.fetchall()
    cur.close()

    debug_print("Models - unconsumed products:", results)

    # Restituisce i risultati come lista di dizionari
    return [{
        "id": row[0], "name": row[1], "barcode": row[2], "quantity": row[3], 
        "inserito": row[4], "scadenza": row[5], "consumo": row[6], "stato": row[7]
    } for row in results]

# Funzione per ottenere l'inventario dei prodotti
def get_product_inventory():
 
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # La query da eseguire
    query = """
        WITH latest_transactions AS (
            -- Prendo tutte le transazioni e gli associo il barcode
            SELECT 
                tf.*,
                p.barcode,
                ROW_NUMBER() OVER (
                    PARTITION BY p.barcode   -- Attenzione: adesso partiziono per BARCODE, non per product_key!
                    ORDER BY tf.ins_date DESC
                ) AS rn
            FROM transaction_fact tf
            LEFT JOIN product_dim p ON tf.product_key = p.id
        ),

        ranked_products AS (
            -- Ora costruisco la lista di prodotti prendendo solo l'ultima transazione per ogni barcode
            SELECT 
                p.id,
                p.name,
                p.barcode,
                p.brand,
                p.shop,
                p.item,
                c.name AS category,
                p.image,
                tf.price,
                tf.quantity,
                tf.ins_date,
                tf.consume_date,
                tf.expiry_date,
                tf.status
            FROM product_dim p
            LEFT JOIN item_list i ON p.item = i.name
            LEFT JOIN category_list c ON i.category_id = c.id
            LEFT JOIN latest_transactions tf ON p.barcode = tf.barcode
            WHERE tf.rn = 1
        )

        SELECT 
            p.barcode,
            p.name,
            p.brand,
            p.shop,
            p.price,
            p.category,
            p.ins_date,
            p.consume_date,
            p.expiry_date,
            p.status,
            
            -- Modificato: ora sommo la quantità reale a magazzino, non conto le righe!
            (
                SELECT COALESCE(SUM(tf2.quantity), 0)
                FROM transaction_fact tf2
                LEFT JOIN product_dim pd2 ON tf2.product_key = pd2.id
                WHERE pd2.barcode = p.barcode
                AND tf2.consume_date IS NULL
            ) AS quantity_in_inventory,
            
            p.image,

            -- Parametri inventory dalla tabella 'inventory'
            s.min_quantity,
            s.max_quantity,
            s.security_quantity,
            s.reorder_point,
            s.mean_usage_time,
            s.reorder_frequency,
            s.user_override

        FROM ranked_products p
        LEFT JOIN inventory s ON s.barcode = p.barcode
        ORDER BY p.barcode;

    """
    # Esegui la query
    cur.execute(query)

    # Recuperare tutti i risultati
    rows = cur.fetchall()

    # Mostrare i record
    for row in rows:
        debug_print(row)

    # Chiudere la connessione
    conn.close()

    # Convertiamo le tuple in una lista di dizionari
    products = [
        {
            "barcode": row[0],
            "name": row[1],
            "brand": row[2],
            "shop": row[3],
            "price": row[4],
            "category": row[5],
            "ins_date": row[6],
            "consume_date": row[7],
            "expiry_date": row[8],
            "status": row[9],
            "quantity_in_inventory": row[10],
            "image": row[11],
            "min_quantity": row[12],
            "max_quantity": row[13],
            "security_quantity": row[14],
            "reorder_point": row[15],
            "mean_usage_time": row[16],
            "reorder_frequency": row[17],
            "user_override": row[18]
        }
        for row in rows
    ]

    return products  # 🔥 Ora restituisce una lista di dizionari! 

def get_product_inventory_by_barcode(barcode):
    debug_print("get_product_inventory_by_barcode: ", barcode)

    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    query = """
        WITH latest_transactions AS (
            SELECT 
                tf.*,
                ROW_NUMBER() OVER (
                    PARTITION BY tf.product_key 
                    ORDER BY tf.ins_date DESC
                ) AS rn
            FROM transaction_fact tf
        ),
        ranked_products AS (
            SELECT 
                p.id,
                p.name,
                p.barcode,
                p.brand,
                p.shop,
                p.item,
                c.name AS category,
                p.image,
                tf.price,
                tf.quantity,
                tf.ins_date,
                tf.consume_date,
                tf.expiry_date,
                tf.status
            FROM product_dim p
            LEFT JOIN item_list i ON p.item = i.name
            LEFT JOIN category_list c ON i.category_id = c.id
            LEFT JOIN latest_transactions tf ON p.id = tf.product_key
            WHERE tf.rn = 1
        )
        SELECT 
            p.barcode,
            p.name,
            p.brand,
            p.shop,
            p.price,
            p.category,
            p.ins_date,
            p.consume_date,
            p.expiry_date,
            p.status,
            (
                SELECT COUNT(*) 
                FROM transaction_fact tf2 
                WHERE tf2.product_key = p.id AND tf2.consume_date IS NULL
            ) AS quantity_in_inventory,
            p.image,

            -- Parametri inventory dalla tabella 'inventory'
            s.min_quantity,
            s.max_quantity,
            s.security_quantity,
            s.reorder_point,
            s.mean_usage_time,
            s.reorder_frequency,
            s.user_override

        FROM ranked_products p
        LEFT JOIN inventory s ON s.barcode = p.barcode
        WHERE p.barcode = ?
    """

    # Esegui la query
    cur.execute(query, (barcode,))
    row = cur.fetchone()  # ⬅️ Prende solo un record

    # Chiudere la connessione
    conn.close()

    # Se non c'è nessun risultato
    if row is None:
        return None

    # Costruisce il dizionario
    product = {
        "barcode": row[0],
        "name": row[1],
        "brand": row[2],
        "shop": row[3],
        "price": row[4],
        "category": row[5],
        "ins_date": row[6],
        "consume_date": row[7],
        "expiry_date": row[8],
        "status": row[9],
        "quantity_in_inventory": row[10],
        "image": row[11],
        "min_quantity": row[12],
        "max_quantity": row[13],
        "security_quantity": row[14],
        "reorder_point": row[15],
        "mean_usage_time": row[16],
        "reorder_frequency": row[17],
        "user_override": row[18]
    }
    
    return product  # ⬅️ Restituisce direttamente il singolo prodotto


def upsert_inventory(data):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Verifica se il record esiste
    cur.execute("SELECT COUNT(*) FROM inventory WHERE barcode = ?", (data['barcode'],))
    record_exists = cur.fetchone()[0] > 0

    if record_exists:
        # Se il record esiste, esegui l'UPDATE
        cur.execute("""
            UPDATE inventory
            SET min_quantity = ?, max_quantity = ?, security_quantity = ?, reorder_point = ?, 
                mean_usage_time = ?, reorder_frequency = ?, user_override = ?
            WHERE barcode = ?
        """, (
            data['min_quantity'], data['max_quantity'], data['security_quantity'], 
            data['reorder_point'], data['mean_usage_time'], data['reorder_frequency'], 
            data['user_override'], data['barcode']
        ))
        debug_print(f"Record con barcode {data['barcode']} aggiornato.")
    else:
        # Se il record non esiste, esegui l'INSERT
        cur.execute("""
            INSERT INTO inventory (barcode, min_quantity, max_quantity, security_quantity, reorder_point,
                                    mean_usage_time, reorder_frequency, user_override)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['barcode'], data['min_quantity'], data['max_quantity'], data['security_quantity'], 
            data['reorder_point'], data['mean_usage_time'], data['reorder_frequency'], data['user_override']
        ))
        debug_print(f"Nuovo record con barcode {data['barcode']} inserito.")

    conn.commit()
    conn.close()


# ✅ AGGIUNGI UN NEGOZIO
def add_shop(name, note=""):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO shop_list (name, note) VALUES (?, ?)", (name, note))
    conn.commit()
    conn.close()

# ✅ OTTIENI TUTTI I NEGOZI
def get_all_shops():
    debug_print("get_all_shops", {Config.DATABASE_PATH})
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, note FROM shop_list")
    shop_list = c.fetchall()
    conn.close()
    return shop_list

def update_shop(shop_id, name, note):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE shop_list
        SET name = ?, note = ?
        WHERE id = ?
    """, (name, note, shop_id))
    conn.commit()
    conn.close()

def delete_shop(shop_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shop_list WHERE id = ?", (shop_id,))
    conn.commit()
    conn.close()

def add_category(name, note):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO category_list (name, note) VALUES (?, ?)", (name, note))
    conn.commit()
    conn.close()

def get_all_categories():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM category_list")
    categories = c.fetchall()
    conn.close()
    return categories

def update_category(category_id, name, note):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("UPDATE category_list SET name = ?, note = ? WHERE id = ?", (name, note, category_id))
    conn.commit()
    conn.close()

def delete_category(category_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM category_list WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()

def add_item(name, note):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO item_list (name, note) VALUES (?, ?)", (name, note))
    conn.commit()
    conn.close()

def update_item(item_id, name, note, category_id):
    debug_print("update_item: ",item_id, name, note, category_id )
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("UPDATE item_list SET name = ?, note = ? , category_id = ? WHERE id = ?", (name, note, category_id, item_id,))
    conn.commit()
    conn.close()

def delete_item(item_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM item_list WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def get_all_items():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    #c.execute("SELECT * FROM item_list")
    c.execute("""
        SELECT s.id, s.name, s.note, c.name AS category_name
        FROM item_list s
        JOIN category_list c ON s.category_id = c.id
     """)
    
    items = c.fetchall()
    conn.close()
    return items


def add_transaction_fact(product_key, barcode, price, quantity, ins_date, consume_date, expiry_date, status):

    debug_print("add_transaction_fact: ", product_key ,barcode, price, quantity, ins_date, consume_date, expiry_date, status)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO transaction_fact (product_key, barcode, price, quantity, ins_date, consume_date, expiry_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_key, barcode, price, quantity, ins_date, consume_date, expiry_date, status
          ))
    conn.commit()
    conn.close()

def update_transaction_fact(id, price, quantity, expiry_date, ins_date):

    debug_print ("update_transaction_fact: ", price, quantity, expiry_date)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE transaction_fact
        SET price=?, quantity=?, expiry_date=?
        WHERE product_key=? AND ins_date=?
    """, (price, quantity,  expiry_date, id, ins_date))
    conn.commit()
    conn.close()

  
def update_transaction_fact_consumed(id, quantity, ins_date, expiry_date, consume_date, status):
    debug_print("update_transaction_fact_consumed:", id, quantity, ins_date, expiry_date, consume_date, status)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    c.execute("""
        UPDATE transaction_fact
        SET quantity=?, consume_date=?, status=?
        WHERE id=? AND ins_date=? AND expiry_date=?
    """, (quantity, consume_date, status, id, ins_date, expiry_date))

    conn.commit()
    conn.close()

def insert_consumed_fact (id, barcode, ins_date, expiry_date):

    consume_date = datetime.now().strftime("%Y-%m-%d")
    debug_print("insert_consumed_fact:", id, barcode, ins_date, consume_date, expiry_date)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO consumed_fact (product_key, barcode, ins_date, consume_date, expiry_date)
        VALUES (?, ?, ?, ?, ?)
    """, (id, barcode, ins_date, consume_date, expiry_date
          ))

    conn.commit()
    conn.close()   


def get_expiring_products(months):
    # Calcola la data limite in base ai mesi forniti
    today = datetime.today()
    expiry_limit = today + timedelta(days=30 * months)
    debug_print(f"Data limite per la scadenza: {expiry_limit}")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    # Query per recuperare i prodotti in scadenza entro la data limite
    c.execute("""
        SELECT 
            trs.id, 
            dim.barcode,
            dim.name, 
            dim.brand, 
            dim.shop, 
            trs.price, 
            cat.name AS category, 
            itl.name AS item,
            trs.quantity,
            trs.ins_date, 
            trs.consume_date, 
            trs.expiry_date, 
            trs.status,  
            dim.image
        FROM transaction_fact trs
        INNER JOIN product_dim dim ON dim.id = trs.product_key
        LEFT JOIN item_list itl ON dim.item = itl.name
        LEFT JOIN category_list cat ON itl.category_id = cat.id
        WHERE trs.expiry_date IS NOT NULL AND trs.expiry_date != '' AND trs.expiry_date <= ?
        ORDER BY trs.expiry_date ASC
    """, (expiry_limit,))

    rows = c.fetchall()

    conn.close()

    # Convertiamo le tuple in una lista di dizionari
    products = [
        {
            "id": row[0],
            "barcode": row[1],
            "name": row[2],
            "brand": row[3],
            "shop": row[4],
            "price": row[5],
            "category": row[6],
            "item": row[7],
            "quantity": row[8],
            "ins_date": row[9],
            "consume_date": row[10],
            "expiry_date": row[11],
            "status": row[12],
            "image": row[13]
        }
        for row in rows
    ]

    return products


# Calcola il numero della settimana corrente
def get_current_week():
    today = datetime.today().date()
    first_day_of_month = today.replace(day=1)

    # Trova il lunedì della settimana che contiene il primo giorno del mese
    start_of_first_week = first_day_of_month - timedelta(days=first_day_of_month.weekday())

    # Calcola la distanza in giorni tra oggi e l'inizio della prima settimana
    days_difference = (today - start_of_first_week).days

    # Settimana reale = ogni 7 giorni da quel primo lunedì
    week_number = days_difference // 7 + 1

    debug_print(f"Numero settimana corrente: {week_number}, Giorno corrente: {today.day}, Primo giorno del mese: {first_day_of_month.day}")
    return week_number



# Calcola l'intervallo di date per la settimana corrente
def get_week_date_range(week_number):
    # Ottieni il primo giorno del mese corrente
    today = datetime.today()
    first_day_of_month = today.replace(day=1)

    # Calcola il lunedì della settimana corrente
    first_monday = first_day_of_month - timedelta(days=first_day_of_month.weekday())

    # Calcola l'inizio e la fine della settimana
    start_date = first_monday + timedelta(weeks=week_number - 1)
    end_date = start_date + timedelta(days=6)

    # Debug: stampa i valori calcolati
    debug_print(f"Week {week_number}: Start Date = {start_date}, End Date = {end_date}")

    return start_date, end_date

# Mainpage, calcola la lista della spesa
def get_shopping_list_data(week_number):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Debug: stampa il numero della settimana
    debug_print(f"get_shopping_list_data - Numero settimana corrente: {week_number}")


    # Query per la settimana 1: Ripristino delle scorte pesanti
    if week_number == 1:
        query = """
            SELECT 
                i.product_key, 
                i.barcode, 
                tf.quantity,
                i.min_quantity, 
                i.max_quantity, 
                i.security_quantity, 
                i.reorder_point, 
                i.mean_usage_time, 
                i.reorder_frequency,
                pd.name,
                pd.shop,
                tf.price
            FROM 
                inventory i
            JOIN 
                transaction_fact tf ON i.barcode = tf.barcode
            JOIN
                product_dim pd ON i.barcode = pd.barcode
            WHERE 
                (i.reorder_point IS NOT NULL AND i.reorder_point > 0) AND
                (i.reorder_frequency >= 30 
                OR tf.quantity < i.security_quantity 
                OR tf.quantity < i.reorder_point 
                OR i.mean_usage_time > 15)
        """
    else:
        # Query per le settimane 2, 3 e 4: Prodotti esauriti o sotto quantità minima
        query = """
            SELECT 
                i.product_key, 
                i.barcode, 
                tf.quantity,
                i.min_quantity, 
                i.max_quantity, 
                pd.name,
                pd.shop,
                tf.price
            FROM 
                inventory i
            JOIN 
                transaction_fact tf ON i.barcode = tf.barcode
            JOIN
                product_dim pd ON i.barcode = pd.barcode
            WHERE 
                tf.quantity = 0 
                OR tf.quantity < i.min_quantity
        """

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    items = []
    shop_totals = {}

    for row in rows:
        # Calcola la quantità da acquistare
        quantity_to_buy = max(row['max_quantity'] - row['quantity'], 1)

        # Calcola il motivo
        motivo = "Riordino programmato"
        if week_number == 1:
            if row['quantity'] is not None and row['security_quantity'] is not None and row['quantity'] < row['security_quantity']:
                motivo = "Sotto scorta"
            elif row['quantity'] is not None and row['reorder_point'] is not None and row['quantity'] < row['reorder_point']:
                motivo = "Vicino al punto di riordino"
            elif row['mean_usage_time'] is not None and row['mean_usage_time'] > 15:
                motivo = "Consumo rapido"
        else:
            motivo = "Esaurito" if row['quantity'] == 0 else "Sotto quantità minima"

        # Crea l'oggetto prodotto
        item = {
            "product_name": row['name'],
            "quantity_to_buy": quantity_to_buy,
            "store_name": row['shop'],
            "motivo": motivo,
            "price": row['price'] or 0  # se price è NULL
        }
        items.append(item)

        # Calcolo totale spesa per negozio
        if item["store_name"]:
            if item["store_name"] not in shop_totals:
                shop_totals[item["store_name"]] = 0
            shop_totals[item["store_name"]] += quantity_to_buy * item["price"]

    return items, shop_totals

# Mainpage, calcola il numero dei prodotti che scadono nel mese corrente
def get_number_expiring_products():
    import datetime
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Calcola il primo e l'ultimo giorno del mese corrente
    current_date = datetime.datetime.now()
    first_day_of_month = current_date.replace(day=1)  # Primo giorno del mese
    last_day_of_month = (first_day_of_month + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)  # Ultimo giorno del mese

    # Formatta le date in formato 'YYYY-MM-DD'
    first_day_str = first_day_of_month.strftime('%Y-%m-%d')
    last_day_str = last_day_of_month.strftime('%Y-%m-%d')

    # Debug: stampa le date calcolate
    print(f"Intervallo di date: {first_day_str} - {last_day_str}")

    # Query per contare i prodotti in scadenza nel mese corrente
    query = """
        SELECT COUNT(*)
        FROM transaction_fact
        WHERE expiry_date BETWEEN ? AND ?
    """
    cursor.execute(query, (first_day_str, last_day_str))
    count = cursor.fetchone()[0]

    # Debug: stampa il risultato della query
    print(f"Numero di prodotti trovati: {count}")

    conn.close()
    return count

# Mainpage, calcola il numero dei prodotti che sono esauriti
def get_out_of_stock_count():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Query per contare i prodotti con quantità pari a 0
    query = """
        SELECT COUNT(*)
        FROM transaction_fact
        WHERE quantity = 0
    """
    cursor.execute(query)
    count = cursor.fetchone()[0]
    debug_print("get_out_of_stock_count: ", count)

    conn.close()
    return count

# Mainpage, calcola il numero dei prodotti che sono in scorte critiche
def get_critical_stock_count():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Query per contare i prodotti con scorte critiche
    query = """
        SELECT COUNT(*)
        FROM transaction_fact tf
        JOIN inventory i ON tf.barcode = i.barcode
        WHERE tf.quantity < i.security_quantity
    """
    cursor.execute(query)
    count = cursor.fetchone()[0]

    conn.close()
    return count

# Mainpage, calcola il numero dei prodotti che sono stati consumati nel mese corrente
def get_monthly_consumed_count():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Ottieni il primo giorno del mese corrente
    query = """
        SELECT COUNT(*)
        FROM consumed_fact
        WHERE strftime('%Y-%m', consume_date) = strftime('%Y-%m', 'now')
    """
    cursor.execute(query)
    count = cursor.fetchone()[0]

    conn.close()
    return count

# Mainpage, calcola il numero dei prodotti che sono da riordinare
def get_reorder_count_from_shopping_list():
    # Usa la funzione esistente per ottenere i dati della lista della spesa
    items, _ = get_shopping_list_data(week_number=1)  # Considera la prima settimana del mese
    return len(items)  # Restituisce il numero totale di prodotti

# Mainpage, calcola il costo totale dei prodotti da riordinare
def get_reorder_total_cost():
    # Usa la funzione esistente per ottenere i dati della lista della spesa
    items, _ = get_shopping_list_data(week_number=1)  # Considera la prima settimana del mese
    total_cost = 0

    # Calcola il costo totale
    for item in items:
        total_cost += item["quantity_to_buy"] * item["price"]  # Prezzo totale per il prodotto

    return round(total_cost, 2)  # Arrotonda a due decimali