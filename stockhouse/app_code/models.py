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
            notes TEXT,
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

    # ✅ CREA TABELLA product_settings che contiene i parametri di configurazione diei prodotti
    c.execute("""
        CREATE TABLE IF NOT EXISTS product_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key INTEGER,  
            barcode TEXT,
            necessity_level TEXT,  -- (es.indispensabile, utile,occasionale,stagionale)
            season TEXT,  -- (es. primavera, estate, autunno, inverno)
            min_quantity INTEGER,
            max_quantity INTEGER,
            security_quantity INTEGER,
            reorder_point INTEGER,
            mean_usage_time INTEGER,
            reorder_frequency INTEGER,
            priority_level INTEGER DEFAULT 2,  -- Valore da 1 (alta priorita`) a 3 (bassa priorita`) viene settato in automatico, funzione di product_type e seasons
            user_override INTEGER DEFAULT 1, -- 1=abilitato, 0=disabilitato
            FOREIGN KEY(product_key) REFERENCES product_dim(id)
        )
    """)
    conn.commit()
 
    # ✅ CREA TABELLA CONFIG che contiene 1 record con i parametri di configurazione
    c.execute("""
        CREATE TABLE IF NOT EXISTS budget_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            budget INTEGER,  
            perc_decade_1 INTEGER DEFAULT 0,  -- Percentuale del budget da spendere nella prima decade del mese  
            perc_decade_2 INTEGER DEFAULT 0,  -- Percentuale del budget da spendere nella seconda decade del mese  
            perc_decade_3 INTEGER DEFAULT 0,  -- Percentuale del budget da spendere nella terza decade del mese
            note TEXT,
            last_update TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S'))  -- Data dell'ultimo aggiornamento 
            )
    """)
    conn.commit()

    # ✅ CREA TABELLA TRANSACTION_FACT che contiene le transazioni dei prodotti
    c.execute("""
        CREATE TABLE IF NOT EXISTS transaction_fact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key INTEGER,
            barcode TEXT,
            price REAL,
            quantity INTEGER,
            consumed_quantity INTEGER DEFAULT 0,  
            ins_date TEXT,
            consume_date TEXT,
            expiry_date TEXT,
            status TEXT,
            FOREIGN KEY (product_key) REFERENCES product_dim(id)
        )
    """)
    conn.commit()


    # ✅ CREA TABELLA shopping_list
    c.execute("""
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT,
            product_name TEXT,
            quantity_to_buy INTEGER,
            shop TEXT,
            reason TEXT,
            price REAL,
            decade_number TEXT,
            insert_date DATE,
            within_budget INTEGER DEFAULT 0,  -- 0 = false, 1 = true
            FOREIGN KEY (barcode) REFERENCES product_dim(barcode)
        )
    """)

    # ✅ CREA INDICE UNIVOCO su barcode e decade_number
    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_shopping_list_barcode_decade
        ON shopping_list (barcode, decade_number)
    """)
    conn.commit()

    # ✅ CREA TABELLA EXPENSES_FACT che contiene la la somma delle spese per giorno e negozio
    c.execute("""
        CREATE TABLE IF NOT EXISTS expenses_fact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shopping_date DATE,            
            decade_number TEXT,
            shop TEXT,
            amount REAL
        )
    """)

    conn.commit()

  # ✅ CREA TABELLA shopping_queue usata come coda di comunicazione con shoppy
    c.execute("""  
        CREATE TABLE IF NOT EXISTS shopping_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            quantity INTEGER,
            price REAL,
            expiry TEXT,
            shop TEXT,
            timestamp TEXT
        )
   """)

    conn.commit()

    # ✅ CREA TABELLA system_state usata per il refresh della shopping list
    c.execute("""  
        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT "1",
            decade TEXT DEFAULT NULL
        )
    """)
    conn.commit()

    # Inserisce il record iniziale se non esiste
    c.execute("""
        INSERT INTO system_state (key, value, decade)
        VALUES ('shopping_list_refresh_needed', '1', NULL)
        ON CONFLICT(key) DO NOTHING;
    """)
    conn.commit()


  # ✅ CREA TABELLA product_alias usata per la identificazione dei prodotti acquistati dagli scontrini
    c.execute("""  
        CREATE TABLE IF NOT EXISTS product_alias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_name TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            shop TEXT NOT NULL,  
            source TEXT DEFAULT 'manual', -- es: 'receipt', 'manual', 'learned'
            confidence_score REAL DEFAULT 1.0, -- tra 0.0 e 1.0
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY (product_id) REFERENCES product_dim(id)
        )

   """)
    conn.commit()

    # ✅ CREA TABELLA unknown_products usata per contenere i prodotti non identificati e che richiedono intervento umano
    c.execute("""  
        CREATE TABLE IF NOT EXISTS unknown_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,   
            raw_name TEXT NOT NULL,
            matched_product_id INTEGER,       -- nullable  
            normalized_name TEXT NOT NULL,
            insert_date TEXT DEFAULT CURRENT_TIMESTAMP,
            traduzione_italiano TEXT,  -- Traduzione italiana del nome
            quantita INTEGER,          -- Quantità acquistata
            prezzo_unitario REAL,      -- Prezzo per unità
            prezzo_totale REAL,         -- Prezzo totale
            note TEXT
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
    
# Esegue Lookup in product_dim sulla base del product_id
def lookup_products_by_id(product_id):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            p.id, 
            p.barcode,
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
        WHERE p.id = ?
    """, (product_id,))

    prodotto = cursor.fetchone()
    conn.close()
  
    debug_print("lookup_products_by_id: ", prodotto)

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
            "image": prodotto[9]
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
            p.barcode,
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
            "barcode": prodotto[1],
            "name": prodotto[2],
            "brand": prodotto[3],
            "shop": prodotto[4],
            "price": prodotto[5],
            "quantity": prodotto[6],
            "category": prodotto[7],
            "item": prodotto[8],
            "image": prodotto[9]
        }
    else:
        return {"found": False}
    
def lookup_products_by_name_ins_date(barcode, ins_date):
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
        LEFT JOIN transaction_fact tf ON p.id = tf.product_key AND DATE(tf.ins_date) = ?
        WHERE p.barcode = ?
    """, (ins_date, barcode))


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

def add_product_dim(barcode, name, brand, shop, category, item, notes, image):

    debug_print(f"Risultato: Barcode={barcode}, Name={name}, Brand={brand}, Shop={shop}, Category={category}, Item={item}, Notes={notes}")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO product_dim (barcode, name, brand, shop, category, item, notes, image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (barcode, name, brand, shop, category, item, notes, image
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

def delete_product_from_db(barcode, ins_date):
    debug_print("delete_product: ", barcode, ins_date)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM transaction_fact WHERE barcode = ? AND ins_date = ?", (barcode, ins_date))
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
                ps.necessity_level,
                ps.season,
                ps.min_quantity,
                ps.max_quantity,
                ps.security_quantity,
                ps.reorder_point,
                ps.mean_usage_time,
                ps.reorder_frequency,
                ps.priority_level,
                ps.user_override,                   
                dim.image
            FROM product_dim dim
            JOIN transaction_fact trs ON dim.id = trs.product_key
            LEFT JOIN item_list itl ON dim.item = itl.name
            LEFT JOIN category_list cat ON itl.category_id = cat.id
            LEFT JOIN product_settings ps ON dim.barcode = ps.barcode
            GROUP BY dim.barcode
            ORDER BY dim.name, trs.ins_date DESC
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
            "necessity_level": row[13],
            "season": row[14],
            "min_quantity": row[15],
            "max_quantity": row[16],
            "security_quantity": row[17],
            "reorder_point": row[18],
            "mean_usage_time": row[19],
            "reorder_frequency": row[20],
            "priority_level": row[21],
            "user_override": row[22],
            "image": row[23]
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

    if expiry_date and expiry_date.lower() not in ("null", ""):   # Se la data di scadenza è fornita
        debug_print("get_product_by_name_and_dates - Data di scadenza fornita")
        query = """
            SELECT tf.id, pd.name, tf.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status
            FROM transaction_fact tf
            JOIN product_dim pd ON tf.product_key = pd.id
            WHERE pd.name = ? AND tf.ins_date = ? AND tf.expiry_date = ?
        """
        params = (name, ins_date, expiry_date)
    else:  # Se la data di scadenza non è fornita
        debug_print("get_product_by_name_and_dates - Data di scadenza non fornita")
        query = """
            SELECT tf.id, pd.name, tf.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status
            FROM transaction_fact tf
            JOIN product_dim pd ON tf.product_key = pd.id
            WHERE pd.name = ? AND tf.ins_date = ? AND (tf.expiry_date IS NULL OR tf.expiry_date='')
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

# Funzione per cercare i prodotti non consumati nel database. La ricerca e` effettuata su barcode e nome prodotto`
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

# Funzione per ottenere la lista completa dei prodotti non consumati sulla base del filtro a tendina (tab3)
def get_unconsumed_products_full_list():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tf.id, pd.name, pd.barcode, tf.ins_date, tf.expiry_date, tf.quantity
        FROM transaction_fact tf 
        JOIN product_dim pd  ON pd.id = tf.product_key
        WHERE tf.status = 'in stock'
        ORDER BY pd.name ASC
    """)
    rows = cursor.fetchall()

    conn.close()
    debug_print("get_unconsumed_products_full_list: ", rows)

    return [{
        'id': row[0],
        'name': row[1],
        'barcode': row[2],
        'ins_date': row[3],
        'expiry_date': row[4],
        'quantity': row[5]
    } for row in rows]



# Funzione per ottenere un record unico non consumato in base a barcode, ins_date e (opzionalmente) expiry_date
def get_unique_unconsumed_record(barcode, ins_date, expiry_date):

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    if expiry_date and expiry_date.lower() != 'null':
        cursor.execute("""
            SELECT pd.id, pd.name, pd.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status 
            FROM transaction_fact tf 
            JOIN product_dim pd  ON pd.id = tf.product_key
            WHERE tf.barcode = ?
              AND tf.ins_date = ?
              AND tf.expiry_date = ?
              AND tf.status = 'in stock'
        """, (barcode, ins_date, expiry_date))
    else:
        cursor.execute("""
            SELECT pd.id, pd.name, pd.barcode, tf.quantity, tf.ins_date, tf.expiry_date, tf.consume_date, tf.status 
            FROM transaction_fact tf 
            JOIN product_dim pd  ON pd.id = tf.product_key
            WHERE tf.barcode = ?
              AND tf.ins_date = ?
              AND tf.expiry_date IS NULL
              AND tf.status = 'in stock'
        """, (barcode, ins_date))

    row = cursor.fetchone()
    conn.close()
    debug_print("get_unique_unconsumed_record: ", row)

    if row:
        return {
            'id': row[0],
            'name': row[1],
            'barcode': row[2],
            'quantity': row[3],
            'inserito': row[4],
            'scadenza': row[5],
            'consumo': row[6],
            'stato': row[7]
        }
    return None




# Funzione per ottenere l'inventario dei prodotti
def get_product_inventory():
 
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Prima operazione: sincronizza inventory_fact con i prodotti
    sync_inventory_fact_with_products()
 

    # La query da eseguire
    query = """
            WITH inventory_data AS (
                SELECT
                    pd.barcode,
                    pd.name,
                    pd.brand,
                    pd.shop,
                    pd.item,
                    c.name AS category,
                    pd.image,
                    tf.price,
                    tf.ins_date,
                    tf.consume_date,
                    tf.expiry_date,
                    (tf.quantity - tf.consumed_quantity) AS quantity_remaining
                FROM transaction_fact tf
                JOIN product_dim pd ON tf.product_key = pd.id
                LEFT JOIN item_list i ON pd.item = i.name
                LEFT JOIN category_list c ON i.category_id = c.id
                WHERE (tf.quantity - tf.consumed_quantity) > 0
            ),
            aggregated_inventory AS (
                SELECT
                    barcode,
                    name,
                    brand,
                    shop,
                    item,
                    category,
                    MAX(image) AS image,
                    MAX(price) AS price,
                    MIN(ins_date) AS ins_date,
                    NULL AS consume_date, -- Placeholder per avere la colonna
                    MIN(expiry_date) AS expiry_date,
                    SUM(quantity_remaining) AS quantity_in_inventory
                FROM inventory_data
                GROUP BY barcode, name, brand, shop, item, category
            )
            SELECT 
                ai.barcode,
                ai.name,
                ai.brand,
                ai.shop,
                ai.price,
                ai.item,
                ai.category,
                ai.ins_date,
                ai.consume_date,
                ai.expiry_date,
                ai.quantity_in_inventory,
                (ai.price * ai.quantity_in_inventory) AS total_value,
                ai.image,
                s.min_quantity,
                s.max_quantity,
                s.security_quantity,
                s.reorder_point,
                s.mean_usage_time,
                s.reorder_frequency,
                s.user_override,
                s.necessity_level,
                s.season
            FROM aggregated_inventory ai
            LEFT JOIN product_settings s ON s.barcode = ai.barcode
            ORDER BY ai.barcode;
    """
    # Esegui la query
    cur.execute(query)

    # Recuperare tutti i risultati
    rows = cur.fetchall()

    # Mostrare i record
    #for row in rows:
    #    debug_print(row)

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
            "item": row[5],
            "category": row[6],
            "ins_date": row[7],
            "consume_date": row[8],
            "expiry_date": row[9],
            # "status": row[10],  # Non è più necessario, ora calcoliamo quantity_in_inventory
            "quantity_in_inventory": row[10],
            "total_value": row[11],
            "image": row[12],
            "min_quantity": row[13],
            "max_quantity": row[14],
            "security_quantity": row[15],
            "reorder_point": row[16],
            "mean_usage_time": row[17],
            "reorder_frequency": row[18],
            "user_override": row[19],
            "necessity_level": row[20],
            "season": row[21]
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
            s.user_override,
            s.necessity_level,
            s.season

        FROM ranked_products p
        LEFT JOIN product_settings s ON s.barcode = p.barcode
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
        "user_override": row[18],
        'necessity_level': row[19],
        'season': row[20]
    }
    
    return product  # ⬅️ Restituisce direttamente il singolo prodotto


# Funzione che cancella i record di transazione più vecchi di 365 giorni
def clean_old_transactions():
    debug_print("clean_old_transactions")
    
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Cancella record con consume_date più vecchia di 365 giorni rispetto ad oggi
    cur.execute("""
        DELETE FROM transaction_fact
        WHERE consume_date IS NOT NULL
        AND julianday('now') - julianday(consume_date) > 365
    """)

    conn.commit()
    conn.close()

# Funzione per aggiornare i parametri di inventario
def update_inventory_mean_usage_time():
    debug_print("update_inventory_mean_usage_time")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Calcola il mean_usage_time (media giorni di consumo) per ogni barcode
    cur.execute("""
        SELECT barcode, AVG(JULIANDAY(consume_date) - JULIANDAY(ins_date)) AS avg_days
        FROM consumed_fact
        WHERE consume_date IS NOT NULL
        GROUP BY barcode
    """)

    avg_records = cur.fetchall()

    for barcode, avg_days in avg_records:
        mean_usage_time = int(avg_days) if avg_days is not None else None
        debug_print(f"Updating barcode {barcode} with mean_usage_time: {mean_usage_time}")

        if mean_usage_time is not None:
            # Esegui l'UPDATE nel tuo inventario (sostituisci il nome della tabella e campo)
            cur.execute("""
                UPDATE product_settings
                SET mean_usage_time = ?
                WHERE barcode = ? and user_override = 1
            """, (mean_usage_time, barcode))

    conn.commit()
    conn.close()

# Funzione per aggiornare i parametri di inventario reorder_frequency
def update_reorder_frequency():
    debug_print("update_reorder_frequency")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Prendi tutti i barcode con override attivo
    cur.execute("""
        SELECT DISTINCT barcode
        FROM product_settings
        WHERE user_override = 1
    """)
    barcodes = [row[0] for row in cur.fetchall()]

    for barcode in barcodes:
        # Prendi tutte le ins_date ordinate
        cur.execute("""
            SELECT ins_date
            FROM transaction_fact
            WHERE barcode = ?
            ORDER BY ins_date ASC
        """, (barcode,))
        rows = cur.fetchall()

        # Calcola le differenze tra date successive
        dates = [datetime.strptime(r[0], "%Y-%m-%d") for r in rows if r[0]]
        if len(dates) < 2:
            continue

        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        avg_gap = int(sum(gaps) / len(gaps)) if gaps else None

        if avg_gap:
            debug_print(f"Updating barcode {barcode} with reorder_frequency: {avg_gap}")
            cur.execute("""
                UPDATE product_settings
                SET reorder_frequency = ?
                WHERE barcode = ? AND user_override = 1
            """, (avg_gap, barcode))

    conn.commit()
    conn.close()



# Funzione per sincronizzare i prodotti in inventory_fact con product_dim
def sync_inventory_fact_with_products():
    debug_print("sync_inventory_fact_with_products")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Leggi tutti i barcode già presenti nella tabella product_settings
    cur.execute("SELECT barcode FROM product_settings")
    existing_barcodes = {row[0] for row in cur.fetchall()}
    #debug_print("existing_barcodes: ", existing_barcodes)

    # Leggi tutti i prodotti dalla tabella product_dim
    cur.execute("SELECT id, barcode FROM product_dim")
    all_products = cur.fetchall()

    # Trova solo quelli i cui barcode NON sono già in inventory
    missing_products = [
        (id_, barcode)
        for (id_, barcode) in all_products
        if barcode not in existing_barcodes
    ]
    #debug_print("missing_products: ", missing_products)

    # Inserisci i prodotti mancanti
    for product_key, barcode in missing_products:
        cur.execute("""
            INSERT INTO product_settings (
                product_key, barcode, user_override
            ) VALUES (?, ?, ?)
        """, (product_key, barcode, 1))

    if missing_products:
        conn.commit()


    conn.close()


def to_int_or_none(value):
    print(f"Valore ricevuto: '{value}' → tipo: {type(value)}")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def upsert_inventory(data):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Verifica se il record esiste
    cur.execute("SELECT id FROM product_dim WHERE barcode = ?", (data['barcode'],))
    product_key = cur.fetchone()
    if product_key:
       product_key = product_key[0]  # Prendi solo l’intero valore, non la tupla

    cur.execute("SELECT COUNT(*) FROM product_settings WHERE barcode = ?", (data['barcode'],))
    record_exists = cur.fetchone()[0] > 0

    if record_exists:
        cur.execute("""
            UPDATE product_settings
            SET min_quantity = ?, max_quantity = ?, security_quantity = ?, reorder_point = ?, 
                mean_usage_time = ?, reorder_frequency = ?, user_override = ?, necessity_level = ?
            WHERE barcode = ?
        """, (
            to_int_or_none(data['min_quantity']),
            to_int_or_none(data['max_quantity']),
            to_int_or_none(data['security_quantity']),
            to_int_or_none(data['reorder_point']),
            to_int_or_none(data['mean_usage_time']),
            to_int_or_none(data['reorder_frequency']),
            data['user_override'],
            data['necessity_level'],     
            data['barcode']
        ))

    else:
        # Se il record non esiste, esegui l'INSERT
        cur.execute("""
            INSERT INTO product_settings (
                product_key, barcode, min_quantity, max_quantity, security_quantity, reorder_point,
                mean_usage_time, reorder_frequency, user_override, necessity_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_key,
            data['barcode'],
            to_int_or_none(data['min_quantity']),
            to_int_or_none(data['max_quantity']),
            to_int_or_none(data['security_quantity']),
            to_int_or_none(data['reorder_point']),
            to_int_or_none(data['mean_usage_time']),
            to_int_or_none(data['reorder_frequency']),
            data['user_override'],
            data['necessity_level']  # 👈 aggiunto qui
        ))



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


def add_transaction_fact(product_key, barcode, price, quantity, consumed_quantity, ins_date, consume_date, expiry_date, status):

    debug_print("add_transaction_fact: ", product_key ,barcode, price, quantity, consumed_quantity, ins_date, consume_date, expiry_date, status)

    # Normalizza expiry_date: se None o stringa vuota, setta a None (che diventa NULL in SQLite)
    if not expiry_date or str(expiry_date).strip() == '':
        expiry_date = None

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO transaction_fact (product_key, barcode, price, quantity, consumed_quantity, ins_date, consume_date, expiry_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_key, barcode, price, quantity, consumed_quantity, ins_date, consume_date, expiry_date, status
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

def upsert_transaction_fact(product_key, barcode, price, quantity, consumed_quantity,
                           ins_date, consume_date, expiry_date, status):
    """
    Inserisce una nuova transazione nella tabella transaction_fact oppure aggiorna
    quella esistente se già presente per lo stesso prodotto e data di inserimento.

    La verifica di esistenza del record si basa su product_key e ins_date, che corrisponde
    alla data dello scontrino.

    Parametri:
    - product_key: identificativo univoco del prodotto
    - barcode: codice a barre del prodotto
    - price: prezzo unitario del prodotto
    - quantity: quantità acquistata
    - consumed_quantity: quantità consumata (inizialmente 0 se nuovo acquisto)
    - ins_date: data di inserimento (data emissione scontrino)
    - consume_date: data di consumo (se disponibile)
    - expiry_date: data di scadenza (se disponibile)
    - status: stato della transazione (es. 'acquistato')

    Se il record esiste già, aggiorna i campi con i nuovi valori.
    Altrimenti inserisce un nuovo record.
    """
    debug_print("upsert_transaction_fact:", product_key, barcode, price, quantity, consumed_quantity,ins_date, consume_date, expiry_date, status)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    # Controlla se esiste già il record con product_key e ins_date
    c.execute("""
        SELECT COUNT(*) FROM transaction_fact
        WHERE product_key = ? AND ins_date = ?
    """, (product_key, ins_date))
    exists = c.fetchone()[0] > 0

    if exists:
        # Aggiorna il record esistente con i nuovi dati
        debug_print("upsert_transaction_fact - Record esistente trovato, aggiornamento in corso...")
        c.execute("""
            UPDATE transaction_fact
            SET price = ?, quantity = ? 
            WHERE product_key = ? AND ins_date = ?
        """, (price, quantity, product_key, ins_date))
    else:
        # Inserisce un nuovo record se non esiste
        debug_print("upsert_transaction_fact - inserimento :", product_key, barcode, price, quantity, consumed_quantity, ins_date, consume_date, expiry_date, status)
        c.execute("""
            INSERT INTO transaction_fact (product_key, barcode, price, quantity, consumed_quantity,
                                         ins_date, consume_date, expiry_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (product_key, barcode, price, quantity, consumed_quantity,
              ins_date, consume_date, expiry_date, status))
        
    #Rimuove dalla lista della spesa
    c.execute("DELETE FROM shopping_list WHERE barcode = ?", (barcode,))
    print(f"[INFO] Prodotto {barcode} rimosso dalla lista della spesa.")    

    conn.commit()
    conn.close()


  
def update_transaction_fact_consumed(id, ins_date, expiry_date):
    debug_print("update_transaction_fact_consumed:", id, ins_date, expiry_date)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    c.execute("""
        UPDATE transaction_fact
        SET
            consumed_quantity = COALESCE(consumed_quantity, 0) + 1,
            status = CASE
                WHEN quantity = COALESCE(consumed_quantity, 0) + 1 THEN 'out of stock'
                ELSE status
            END,
            consume_date = CASE
                WHEN quantity = COALESCE(consumed_quantity, 0) + 1 THEN DATE('now')
                WHEN quantity < COALESCE(consumed_quantity, 0) + 1 THEN NULL
                ELSE consume_date
            END
            WHERE id = ?
            AND ins_date = ?
            AND (expiry_date = ? OR expiry_date IS NULL OR TRIM(expiry_date) = '')
    """, (id, ins_date, expiry_date))
    conn.commit()
    conn.close()

def insert_consumed_fact (id, barcode, ins_date, expiry_date):

    consume_date = datetime.now().strftime("%Y-%m-%d")
    debug_print("insert_consumed_fact:", id, barcode, ins_date, consume_date, expiry_date)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    # Verifica se il prodotto esiste nella tabella product_dim
    c.execute("""
         INSERT INTO consumed_fact (product_key, barcode, ins_date, consume_date, expiry_date)
            VALUES ((SELECT id FROM product_dim WHERE barcode = ?), ?, ?, ?, ?)
    """, (barcode, barcode, ins_date, consume_date, expiry_date))

    conn.commit()
    conn.close()   


def delete_from_shopping_list(barcode):
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()
    debug_print("delete_from_shopping_list: ", barcode)
    c.execute("DELETE FROM shopping_list WHERE barcode = ?", (barcode,))
    conn.commit()
    conn.close()



def delete_unknown_product_by_name(name):
    """
    Elimina un record dalla tabella 'unknown_products' in base al nome del prodotto.
    Questa funzione è utile quando un prodotto precedentemente sconosciuto viene 
    riconosciuto e correttamente inserito nel database dei prodotti principali.
    """
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    debug_print("delete from unknown_products: ", name)
    cursor.execute("""
                    DELETE FROM unknown_products
                    WHERE raw_name = ?
                """, (name,))
    conn.commit()
    conn.close()



# Funzione per inserire un alias di prodotto se non esiste già
def insert_product_alias_if_not_exists(name, barcode, shop):
  
    normalized_alias = name.lower().replace(" ", "")
    debug_print("insert_product_alias_if_not_exists: ", name, "alias:", normalized_alias)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Recupera il product_id da product_dim
    cursor.execute("SELECT id FROM product_dim WHERE barcode = ?", (barcode,))
    result = cursor.fetchone()
    if result is None:
        debug_print(f"⚠️ Nessun prodotto trovato con barcode {barcode}")
        return
    product_id = result[0]


    # Verifica se l'alias esiste già
    cursor.execute("""
        SELECT 1 FROM product_alias 
        WHERE normalized_alias = ? AND product_id = ? AND shop = ?
    """, (normalized_alias, product_id, shop))
    if cursor.fetchone():
        print(f"ℹ️ Alias già esistente: {normalized_alias}")
        return
    
    source = "new product"
    confidence_score = 1

    # Inserisci nuovo alias
    cursor.execute("""
        INSERT INTO product_alias (
            alias_name, normalized_alias, product_id, shop, source, confidence_score
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (name, normalized_alias, product_id, shop, source, confidence_score))
    debug_print(f"✅ Alias inserito: {name} ({normalized_alias}) per prodotto ID {product_id}")

    
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
        WHERE trs.status = "in stock" AND trs.expiry_date IS NOT NULL AND trs.quantity > 0 AND trs.expiry_date != '' AND trs.expiry_date <= ?
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
        WHERE status = "in stock" AND expiry_date BETWEEN ? AND ?
    """
    cursor.execute(query, (first_day_str, last_day_str))
    count = cursor.fetchone()[0]

    # Debug: stampa il risultato della query
    print(f"Numero di prodotti trovati: {count}")

    conn.close()
    return count


# Funzione per ottenere i prodotti in scadenza nel mese corrente per la home page
def get_expiring_products_for_home():

    import datetime
   # Calcola il primo e l'ultimo giorno del mese corrente
    current_date = datetime.datetime.now()
    first_day_of_month = current_date.replace(day=1)  # Primo giorno del mese
    last_day_of_month = (first_day_of_month + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)  # Ultimo giorno del mese

    # Formatta le date in formato 'YYYY-MM-DD'
    first_day_str = first_day_of_month.strftime('%Y-%m-%d')
    last_day_str = last_day_of_month.strftime('%Y-%m-%d')

    debug_print(f"Data limite per la scadenza (Home): {first_day_str},  {last_day_str}")
    
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    # Query ottimizzata per recuperare solo le colonne necessarie
    query = """
        SELECT 
            dim.name, 
            dim.barcode,
            trs.expiry_date, 
            trs.quantity
        FROM transaction_fact trs
        INNER JOIN product_dim dim ON dim.id = trs.product_key
        WHERE trs.expiry_date IS NOT NULL 
          AND trs.status = "in stock"
          AND trs.expiry_date BETWEEN ? AND ?
        ORDER BY trs.expiry_date ASC
    """
    c.execute(query, (first_day_str, last_day_str))
    rows = c.fetchall()
    conn.close()

    # Convertiamo le tuple in una lista di dizionari
    debug_print("get_expiring_products_for_home - Rows: ", rows)
    products = [
        {
            "name": row[0],
            "barcode": row[1],
            "expiry_date": row[2],
            "quantity": row[3]
        }
        for row in rows
    ]

    return products







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



#Mainpage, Funzione per ottenere i prodotti esauriti
def get_out_of_stock_products():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    # Calcola il primo e l'ultimo giorno del mese corrente
    today = datetime.today()
    first_day = today.replace(day=1)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    debug_print(f"Primo giorno del mese: {first_day}, Ultimo giorno del mese: {last_day}")

    # Query per recuperare i prodotti esauriti nel mese corrente
    c.execute("""
        SELECT 
            dim.name, 
            dim.barcode, 
            dim.category
        FROM transaction_fact trs
        INNER JOIN product_dim dim ON dim.id = trs.product_key
        WHERE trs.quantity - trs.consumed_quantity = 0
          AND trs.consume_date BETWEEN ? AND ?
        ORDER BY dim.name ASC
    """, (first_day, last_day))

    rows = c.fetchall()
    conn.close()

    # Converti i risultati in una lista di dizionari
    products = [
        {
            "name": row[0],
            "barcode": row[1],
            "category": row[2]
        }
        for row in rows
    ]

    return products

# Mainpage, calcola il numero dei prodotti che sono esauriti
def get_out_of_stock_count():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Calcola il primo e l'ultimo giorno del mese corrente
    today = datetime.today()
    first_day = today.replace(day=1)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    debug_print(f"Primo giorno del mese: {first_day}, Ultimo giorno del mese: {last_day}")

    # Query per contare i prodotti esauriti nel mese corrente
    query = """
        SELECT COUNT(*)
        FROM transaction_fact trs
        INNER JOIN product_dim dim ON dim.id = trs.product_key
        WHERE trs.quantity - trs.consumed_quantity = 0
          AND trs.consume_date BETWEEN ? AND ?
    """
    cursor.execute(query, (first_day, last_day))
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
        FROM (
                SELECT tf.barcode, 
                SUM(tf.quantity) - COALESCE(SUM(tf.consumed_quantity),0) AS tot
                FROM transaction_fact tf
                JOIN product_settings i ON tf.barcode = i.barcode
                GROUP BY tf.barcode
                HAVING tot < i.security_quantity
             )
    """
    cursor.execute(query)
    count = cursor.fetchone()[0]

    conn.close()
    return count

# Mainpage, seleziona i prodotti che sono in scorte critiche
def get_critical_stock():

    # Calcola la data limite in base ai mesi forniti
    today = datetime.today()
    expiry_limit = today + timedelta(days=30 * 1)  # 1 mesi
    debug_print(f"get_critical_stock - Data limite per la scadenza (Home): {expiry_limit}")
    
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    # Query ottimizzata per recuperare solo le colonne necessarie
    c.execute("""
        SELECT dim.name, 
                dim.barcode,
                tf.quantity,
                inv.security_quantity, 
                SUM(tf.quantity) - COALESCE(SUM(tf.consumed_quantity),0) AS tot
        FROM transaction_fact tf
        JOIN product_dim dim ON tf.barcode = dim.barcode
        JOIN product_settings inv ON tf.barcode = inv.barcode
        GROUP BY tf.barcode
        HAVING tot < inv.security_quantity  
        ORDER BY dim.name ASC
    """)

    rows = c.fetchall() 
    conn.close()

    # Convertiamo le tuple in una lista di dizionari
    debug_print("get_expiring_products_for_home - Rows: ", rows)
    products = [
        {
            "name": row[0],
            "barcode": row[1],
            "quantity": row[4],  # ritorna Tot
            "security_quantity": row[3]
        }
        for row in rows
    ]

    return products

def get_unknown_products():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT raw_name, normalized_name, insert_date, 
               COALESCE(CAST(matched_product_id AS TEXT), 'N/D'), 
               COALESCE(note, '')
        FROM unknown_products
        ORDER BY insert_date DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

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

# Mainpage, calcola il numero dei prodotti che sono stati consumati nel mese corrente
def get_monthly_consumed_statistics():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Ottieni il primo giorno del mese corrente
    query = """
        SELECT dim.name,
               cons.ins_date,
               cons.consume_date,
               cons.expiry_date
        FROM consumed_fact cons
        INNER JOIN product_dim dim ON dim.id = cons.product_key
        WHERE cons.consume_date BETWEEN date('now', 'start of month') AND date('now')
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # Convertiamo le tuple in una lista di dizionari
    debug_print("get_monthly_consumed_statistics - Rows: ", rows)
    products = [
        {
            "name": row[0],
            "ins_date": row[1],
            "consume_date": row[2],
            "expiry_date": row[3]
        }
        for row in rows
    ]

    return products


# Budget - Setta il budget mensile. La tabella prevede un solo record
def upsert_budget(id, budget, perc_decade_1, perc_decade_2, perc_decade_3, note):
    
    debug_print("upsert_budget:", id, budget, note)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Verifica se il record esiste
    cur.execute("SELECT * FROM budget_config WHERE id = ?", (id,))
    row = cur.fetchone()
    record_exists = row is not None and row[0] > 0
 
    if record_exists:
        # Se il record esiste, esegui l'UPDATE
        debug_print("Record esistente, esegui l'UPDATE", id, budget, perc_decade_1, perc_decade_2, perc_decade_3, note)
        cur.execute("""
            UPDATE budget_config
            SET budget = ?, perc_decade_1 = ?, perc_decade_2 = ?, perc_decade_3 = ?, note = ?
            WHERE id = ?
        """, (budget, perc_decade_1, perc_decade_2, perc_decade_3, note, id)
        )
    else:
        # Se il record non esiste, esegui l'INSERT
        debug_print("Record non esistente, esegui l'INSERT")
        cur.execute("""
            INSERT INTO budget_config (id, budget, perc_decade_1, perc_decade_2, perc_decade_3, note)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id, budget, perc_decade_1, perc_decade_2, perc_decade_3, note)
        )
 
    conn.commit()

    conn.close()

# Budget - Restituisce il record inserito
def get_budget():
    id = 1
    debug_print("get_budget:", id)

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Verifica se il record esiste
    cur.execute("SELECT budget, perc_decade_1, perc_decade_2, perc_decade_3, note, last_update FROM budget_config WHERE id = ?", (id,))
    row = cur.fetchone()

    conn.close()

    if row:
        budget = {
            "budget": row[0],
            "perc_decade_1": row[1],
            "perc_decade_2": row[2],
            "perc_decade_3": row[3],
            "note": row[4],
            "last_update": row[5]
        }
    else:
        budget = None  # oppure puoi restituire un dizionario vuoto

    debug_print("get_budget - Budget: ", budget)
    return budget

# Ricalcola le priorità per tutti i prodotti stagionali. E` un refresche eseguito ad ogni cambio decade.`
def recalculate_seasonal_priorities():
    debug_print("Ricalcolo priorità per tutti i prodotti stagionali (tabella product_settings)...")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Seleziona tutti i prodotti stagionali
    cursor.execute("""
        SELECT barcode, necessity_level, season
        FROM product_settings
        WHERE LOWER(necessity_level) = 'stagionale'
    """)
    products = cursor.fetchall()

    count = 0
    for barcode, necessity_level, season in products:
        try:
            # Calcola la priorità per ciascun prodotto
            priority = get_priority_level(barcode, necessity_level, season)
            cursor.execute("""
                UPDATE product_settings
                SET priority_level = ?
                WHERE barcode = ?
            """, (priority, barcode))
            count += 1
        except Exception as e:
            debug_print(f"Errore nel ricalcolo priorità per barcode {barcode}: {e}")

    conn.commit()
    conn.close()

    debug_print(f"Ricalcolo priorità stagionali completato. Prodotti aggiornati: {count}")



# Funzione per calcolare il livello di priorità in base alla stagione
def get_priority_level(barcode, necessity_level, product_seasons, override_data={}):

    seasons_circle = ['primavera', 'estate', 'autunno', 'inverno']
    
    product = get_product_inventory_by_barcode(barcode)

    # Coalesce intelligente: preferisce override_data, altrimenti product
    def get_value(key, fallback=0):
        if key in override_data and override_data[key] is not None:
            return int(override_data[key])
        return int(product.get(key, fallback))

    quantity = get_value("quantity_in_inventory")
    security_quantity = get_value("security_quantity")
    reorder_point = get_value("reorder_point")

    debug_print("get_priority_level - necessity_level:", necessity_level)
    debug_print("get_priority_level - quantity:", quantity, "security_quantity:", security_quantity, "reorder_point:", reorder_point)

    if not necessity_level:
        return 3

    necessity = necessity_level.lower()

    if necessity == 'indispensabile':
        try:
            if quantity <= security_quantity:
                return 1  # Crisi
            elif quantity < reorder_point:
                return 2  # Attenzione
            elif quantity == reorder_point:
                return 3  # Punto di riordino
            else:
                return 4  # Abbondanza
        except Exception as e:
            debug_print("Errore nel calcolo priorità indispensabile:", e)
            return 1
    

    # 2. Utile → priorità 2 fissa
    if necessity == 'utile':
        try:
            quantity = int(product.get("quantity_in_inventory", 0))
            security_quantity = int(product.get("security_quantity", 0))
            reorder_point = int(product.get("reorder_point", 0))

            if quantity <= security_quantity:
                return 3  # attenzione: sta finendo
            elif quantity < reorder_point:
                return 4  # ancora abbondante, ma occhio
            else:
                return 5  # abbondanza, può aspettare
        except Exception as e:
            debug_print("Errore nel calcolo priorità utile:", e)
            return 3  # fallback a priorità attenzione


    # 3. Occasionale → priorità 4 fissa (bassa)
    if necessity == 'occasionale':
        try:
            quantity = int(product.get("quantity_in_inventory", 0))
            security_quantity = int(product.get("security_quantity", 0))
            reorder_point = int(product.get("reorder_point", 0))

            if quantity <= security_quantity:
                return 4  # poco, serve attenzione bassa
            elif quantity < reorder_point:
                return 5  # abbondante, bassissima priorità
            else:
                return 6  # super abbondante, praticamente ignorabile
        except Exception as e:
            debug_print("Errore nel calcolo priorità occasionale:", e)
            return 4  # fallback priorità base

    # 4. Stagionale → dipende dalla stagione
    if necessity == 'stagionale':
        month = datetime.now().month
        if month in [3, 4, 5]:
            current_season = 'primavera'
        elif month in [6, 7, 8]:
            current_season = 'estate'
        elif month in [9, 10, 11]:
            current_season = 'autunno'
        else:
            current_season = 'inverno'

        product_seasons = [s.strip().lower() for s in product_seasons.split(',') if s.strip()]
        curr_index = seasons_circle.index(current_season)

        distances = []
        for season in product_seasons:
            if season in seasons_circle:
                season_index = seasons_circle.index(season)
                distance = min((season_index - curr_index) % 4, (curr_index - season_index) % 4)
                if distance == 0:
                    distances.append(1)  # Stagione corrente → priorità 3
                elif distance == 1:
                    distances.append(2)  # Vicina → priorità 4
                else:
                    distances.append(3)  # Lontana → ignorabile per ora

        return min(distances) if distances else 5

    # Fallback
    return 3

# Funzione per inserire o aggiornare un record di spesa
def upsert_expense(cursor, shopping_date, decade_number, shop, amount, mode="barcode"):
    debug_print("upsert_expense:", shopping_date, decade_number, shop, amount, mode)

    # Pulizia record vecchi sempre
    cursor.execute("""
        DELETE FROM expenses_fact
        WHERE shopping_date < date('now', '-1 year')
    """)

    cursor.execute("""
        SELECT id, amount FROM expenses_fact
        WHERE shopping_date = ? AND decade_number = ? AND shop = ?
    """, (shopping_date, decade_number, shop))
    row = cursor.fetchone()

    if row:
        if mode == "barcode":
            # Somma amount esistente

            cursor.execute("""
                UPDATE expenses_fact
                SET amount = amount + ?
                WHERE id = ?
            """, (amount, row[0]))
        elif mode == "receipt":
            # Sovrascrivi amount esistente
            debug_print("Sovrascrivo amount esistente per receipt")
            cursor.execute("""
                UPDATE expenses_fact
                SET amount = ?
                WHERE id = ?
            """, (amount, row[0]))
    else:
        cursor.execute("""
            INSERT INTO expenses_fact (shopping_date, decade_number, shop, amount)
            VALUES (?, ?, ?, ?)
        """, (shopping_date, decade_number, shop, amount))


# Seleziona i prodotti da visualizzare nella pagina pharmacy.html
def get_pharmacy():
    debug_print("Get_Pharmacy")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT 
            dim.name, 
            dim.notes,
            dim.brand, 
            dim.shop, 
            trs.price, 
            trs.quantity,
            trs.expiry_date, 
            trs.status,          
            dim.image
        FROM transaction_fact trs
        INNER JOIN product_dim dim ON dim.id = trs.product_key
        LEFT JOIN item_list itl ON dim.item = itl.name   
        LEFT JOIN category_list cat ON itl.category_id = cat.id
        WHERE cat.name = '⚕️ Primo soccorso' AND trs.status = "in stock" AND trs.quantity > 0
        ORDER BY trs.expiry_date ASC
    """)

    rows = c.fetchall()
    conn.close()

    products = []
    for row in rows:
        expiry_raw = row[6]
        try:
            expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date() if expiry_raw else None
        except ValueError:
            expiry_date = None  # fallback in caso di formato errato

        products.append({
            "name": row[0],
            "notes": row[1],
            "brand": row[2],
            "shop": row[3],
            "price": row[4],
            "quantity": row[5],
            "expiry_date": expiry_date,
            "status": row[7],
            "image": row[8]
        })

    return products

