from datetime import datetime, timedelta, date
import sqlite3
from stockhouse.app_code.models import get_week_date_range, upsert_expense
from config import Config  # usa il path corretto se è diverso
from stockhouse.utils import debug_print
import calendar


# Funzione per calcolare il numero della decade corrente
def get_current_decade(today=None):
    today = today or datetime.today()
    day = today.day
    if day <= 10:
        return "D1"
    elif day <= 20:
        return "D2"
    else:
        return "D3"

def format_decade_label(decade_number, year=None, month=None):
    # decade_number: "D1", "D2", "D3"
    if year is None or month is None:
        today = datetime.today()
        year = today.year
        month = today.month

    # Calcola l'ultimo giorno del mese (gestisce anche anni bisestili)
    last_day = calendar.monthrange(year, month)[1]

    labels = {
        "D1": f"1ª Decade (1-10)",
        "D2": f"2ª Decade (11-20)",
        "D3": f"3ª Decade (21-{last_day})"
    }
    return labels.get(decade_number, "Decade sconosciuta")

# Funzione per calcolare il budget per la decade corrente
def get_budget_for_decade(total_budget, decade):
    # Distribuzione modificabile come vuoi
    budget_distribution = {
        1: 0.30,  # 30% del budget nella 1ª decade
        2: 0.30,  # 30% nella 2ª
        3: 0.40   # 40% nell'ultima
    }
    return round(total_budget * budget_distribution.get(decade, 0), 2)



# Funzioni per la gestione della lista della spesa
def get_spese_settimanali(database_path, year, month):
    """
    Restituisce un dizionario con le spese settimanali per il mese indicato.
    
    Args:
        database_path (str): Percorso al database SQLite.
        year (int): Anno di riferimento.
        month (int): Mese di riferimento.

    Returns:
        dict: {numero_settimana: totale_spesa}
    """
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            strftime('%W', ins_date) AS week_number,
            SUM(price * quantity) AS totale
        FROM transaction_fact
        WHERE strftime('%Y', ins_date) = ?
          AND strftime('%m', ins_date) = ?
        GROUP BY week_number
    """

    cursor.execute(query, (str(year), f"{month:02d}"))
    rows = cursor.fetchall()
    conn.close()

    spese = {}
    for row in rows:
        # `%W` restituisce settimana ISO, che inizia da 00: noi usiamo 1-based
        week_num = int(row['week_number']) - int(datetime(year, month, 1).strftime('%W')) + 1
        spese[week_num] = round(row['totale'], 2)

    return spese


# Funzioni utili per la gestione settimanale della lista della spesa
def is_last_week_with_25(week_number):

    start_date, end_date = get_week_date_range(week_number)
    return any(day >= 25 for day in range(start_date.day, end_date.day + 1))


def get_spesa_per_decade():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    spese = []
    current_month = datetime.today().strftime("%Y-%m")

    for decade in ['D1', 'D2', 'D3']:
        cursor.execute("""
            SELECT IFNULL(SUM(amount), 0) FROM expenses_fact
            WHERE strftime('%Y-%m', shopping_date) = ? AND decade_number = ?
        """, (current_month, decade))
        totale = cursor.fetchone()[0]
        spese.append(totale)

    conn.close()
    return spese


def get_budget_info():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT budget, perc_decade_1, perc_decade_2, perc_decade_3, note 
        FROM budget_config 
        ORDER BY id DESC LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'budget': float(row['budget']),
            'decade1': int(row['perc_decade_1']),
            'decade2': int(row['perc_decade_2']),
            'decade3': int(row['perc_decade_3']),
            'note': row['note']
        }
    else:
        return {
            'budget': 0,
            'decade1': 0,
            'decade2': 0,
            'decade3': 0,
            'note': ''
        }

    

def get_total_spesa_corrente():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT SUM(quantity * price) FROM transaction_fact")
    result = cursor.fetchone()
    conn.close()

    return float(result[0]) if result and result[0] else 0

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



def parse_quantity(value):
    try:
        if value is None or str(value).strip() == '' or str(value).strip() == '-':
            return 0
        return int(str(value).strip())
    except (ValueError, TypeError):
        return 0



# Funzione per ottenere i dati della lista della spesa
def get_shopping_list_data(save_to_db=False, conn=None, cursor=None, decade=None):
 
    
    debug_print("get_shopping_list_data, save_to_db:", save_to_db, "decade:", decade)

    external_connection = False
    if conn is None or cursor is None:
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        external_connection = True

    # Usa decade passata oppure calcola quella corrente
    decade = decade or get_current_decade()
    debug_print(f"📆 Decade corrente/elaborata: {decade}")

    # Recupera le info di budget dal DB
    budget_info = get_budget_info()
    monthly_budget = budget_info['budget']

    # Percentuali budget per decade prese da DB
    if decade == "D1":
        budget = monthly_budget * (budget_info['decade1'] / 100)
    elif decade == "D2":
        budget = monthly_budget * (budget_info['decade2'] / 100)
    else:
        budget = monthly_budget * (budget_info['decade3'] / 100)

    debug_print(f"💰 Budget disponibile per la {decade}: {budget:.2f}")

    # Query specifica per decade
    if decade == "D3":
        # Ultima decade: reintegro scorte a lunga conservazione o ad alta priorità
        query = """
            SELECT 
                i.barcode,
                stock.total_quantity  AS quantity,
                i.reorder_point, i.min_quantity, i.max_quantity, i.security_quantity,
                pd.name, pd.shop, tf.price,
                i.necessity_level, i.priority_level,
                MAX(tf.expiry_date) as expiry_date,
                MAX(tf.ins_date) as ins_date
            FROM product_settings i
            JOIN (
                SELECT barcode, SUM(quantity) AS total_quantity
                FROM transaction_fact
                WHERE status = 'in stock'
                GROUP BY barcode
                ) AS stock ON i.barcode = stock.barcode
            JOIN transaction_fact tf ON i.barcode = tf.barcode
            JOIN product_dim pd ON i.barcode = pd.barcode
            WHERE 
                i.max_quantity > 0
                AND pd.item NOT LIKE '%Frutta'
                AND pd.item NOT LIKE '%Verdura'
                AND (JULIANDAY(tf.expiry_date) - JULIANDAY(tf.ins_date)) > 30
                AND tf.ins_date >= date('now', '-6 months')
            GROUP BY i.barcode
            HAVING 
                stock.total_quantity < i.reorder_point
                OR stock.total_quantity <= i.security_quantity
            ORDER BY i.priority_level ASC, tf.price ASC
        """
    elif decade == "D1": 
        # Prima decade: prodotti freschi e indispensabili
        query = """
            SELECT 
                i.barcode,
                COALESCE(stock.total_quantity, 0) AS quantity,
                i.reorder_point, i.min_quantity, i.max_quantity, i.security_quantity,
                pd.name, pd.shop, tf_min.price, pd.category,
                i.necessity_level, i.priority_level,
                tf_min.ins_date
            FROM product_settings i
            LEFT JOIN (
                SELECT barcode, 
                    SUM(CASE 
                            WHEN status = 'in stock' THEN quantity
                            WHEN status = 'consumed' THEN -quantity
                            ELSE 0
                        END) AS total_quantity
                FROM transaction_fact
                GROUP BY barcode
            ) stock ON i.barcode = stock.barcode
            JOIN product_dim pd ON i.barcode = pd.barcode
            LEFT JOIN (
                SELECT barcode, MIN(ins_date) AS ins_date, MIN(price) AS price
                FROM transaction_fact
                GROUP BY barcode
            ) tf_min ON i.barcode = tf_min.barcode
            WHERE i.max_quantity > 0 AND i.priority_level=1
            AND (
                (i.necessity_level = 'Indispensabile' AND COALESCE(stock.total_quantity, 0) <= i.security_quantity)
                OR
                (pd.category LIKE '%Alimenti freschi%' AND COALESCE(stock.total_quantity, 0) < i.min_quantity)
                OR
                (pd.category LIKE '%Alimenti Congelati%' AND COALESCE(stock.total_quantity, 0) < i.min_quantity)
            )
            ORDER BY 
                CASE 
                    WHEN 1 = 1 AND (pd.category LIKE '%Alimenti freschi%' OR pd.category LIKE '%Alimenti Congelati%') THEN 0
                    ELSE i.priority_level
                END ASC,
                tf_min.ins_date ASC,
                tf_min.price ASC
        """
    else:
        # Seconda decade: prodotti freschi e indispensabili e utilo avendo piu budget
        query = """
            SELECT
            i.barcode,
            stock.total_quantity AS quantity,
            i.reorder_point, i.min_quantity, i.max_quantity, i.security_quantity,
            pd.name, pd.shop, tf.price,
            i.necessity_level, i.priority_level,
            MIN(tf.ins_date) as ins_date
            FROM product_settings i
            JOIN (
            SELECT barcode, SUM(quantity) AS total_quantity
            FROM transaction_fact
            WHERE status = 'in stock'
            GROUP BY barcode
            ) AS stock ON i.barcode = stock.barcode
            JOIN transaction_fact tf ON i.barcode = tf.barcode
            JOIN product_dim pd ON i.barcode = pd.barcode
            WHERE i.max_quantity > 0
            GROUP BY i.barcode
            HAVING (
            (i.necessity_level = 'Indispensabile' AND stock.total_quantity <= i.reorder_point)
            OR
            (i.necessity_level = 'Utile' AND stock.total_quantity < i.min_quantity)
            OR
            (pd.category LIKE "%Alimenti Freschi" AND stock.total_quantity < i.min_quantity)
            )
            ORDER BY i.priority_level ASC, ins_date ASC, tf.price ASC;
        """




    cursor.execute(query)
    rows = cursor.fetchall()

    items = []
    shop_totals = {}
    total_cost = 0

    for row in rows:
        barcode = row["barcode"]
        product_name = row["name"]
        shop = row["shop"]
        price = row["price"] or 0
        quantity = parse_quantity(row["quantity"])
        max_q = parse_quantity(row["max_quantity"])
        min_q = parse_quantity(row["min_quantity"])
        sec_q = parse_quantity(row["security_quantity"])
        reorder_point = parse_quantity(row["reorder_point"])
        necessity_level = row["necessity_level"]
        quantity_to_buy = 1
        reason = ""

        if necessity_level == "Indispensabile" and quantity < sec_q:
            if decade == "D3":
                quantity_to_buy = max(max_q - quantity, 1)
                reason = "Reintegro scorte"
            else:
                quantity_to_buy = max(sec_q - quantity, 1)
                reason = "Sotto scorta"
            debug_print(f"Prodotto {product_name} è Indispensabile, sotto scorta: {quantity} < {sec_q}")
        elif necessity_level == "Stagionale" and quantity < min_q:
            quantity_to_buy = max(min_q - quantity, 1)
            reason = "Da consumare"
            debug_print(f"Prodotto {product_name} è Stagionale, da consumare: {quantity} < {min_q}")
        elif max_q > quantity and quantity <= reorder_point:
            quantity_to_buy = max(max_q - quantity, 1)
            reason = "Reintegro scorte"
            debug_print(f"Prodotto {product_name} è in Reintegro scorte: {quantity} < {reorder_point}")

        product_cost = quantity_to_buy * price
        if total_cost + product_cost <= budget:
            within_budget = 1
            total_cost += product_cost
        else:
            within_budget = 0

        debug_print(f"Prodotto: {product_name}, Quantità da acquistare: {quantity_to_buy}, Ragione: {reason}, Prezzo unitario: {price:.2f}€, Costo totale: {product_cost:.2f}€, Budget rimanente: {budget - total_cost:.2f}€")

        item = {
            "barcode": barcode,
            "product_name": product_name,
            "quantity_to_buy": quantity_to_buy,
            "shop": shop,
            "reason": reason,
            "price": price,
            "decade_number": decade,
            "within_budget": within_budget
        }
        items.append(item)
        debug_print(f"Aggiunto prodotto alla lista della spesa: {item}")



    debug_print("save_to_db, decade:", decade)

    if save_to_db:
        cursor.execute("DELETE FROM shopping_list WHERE decade_number != ?", (decade,))
    for item in items:
        # Controlla se il record è già presente per la stessa decade e barcode
        cursor.execute("""
            SELECT 1 FROM shopping_list 
            WHERE barcode = ? AND decade_number = ?
        """, (item["barcode"], item["decade_number"]))
        exists = cursor.fetchone()

        if not exists:
            debug_print(f"Prodotto {item['product_name']} non presente, lo aggiungo alla lista della spesa.")
            cursor.execute("""
                INSERT INTO shopping_list (
                    barcode, product_name, quantity_to_buy,
                    shop, reason, price, decade_number, insert_date, within_budget
                ) VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'), ?)
            """, (
                item["barcode"], item["product_name"], item["quantity_to_buy"],
                item["shop"], item["reason"], item["price"], item["decade_number"], item["within_budget"]
            ))
        else:
            debug_print(f"Prodotto {item['product_name']} già presente, lo aggiorno nella lista della spesa.")
            # Se già presente, aggiorna quantità, prezzo e within_budget
            cursor.execute("""
                UPDATE shopping_list SET
                    quantity_to_buy = ?,
                    price = ?,
                    within_budget = ?,
                    insert_date = DATE('now')
                WHERE barcode = ? AND decade_number = ?
            """, (
                item["quantity_to_buy"],
                item["price"],
                item["within_budget"],
                item["barcode"],
                item["decade_number"]
            ))

        conn.commit()

    # Recupera tutti gli elementi della lista della spesa
    cursor.execute("SELECT * FROM shopping_list WHERE within_budget = 1")
    items = cursor.fetchall() 

    shop_totals = {}
    for item in items:
        debug_print(f"Elaboro prodotto: {item['product_name']}, Ragione: {item['reason']}, Quantità da acquistare: {item['quantity_to_buy']}, Prezzo unitario: {item['price']:.2f}€")

        shop = item["shop"]  # oppure item['shop'] se items è una lista di dict
        product_cost = item["price"] * item["quantity_to_buy"]
        if shop:
            shop_totals.setdefault(shop, 0)
            shop_totals[shop] += product_cost

    if external_connection:
        conn.close()

    debug_print(f"🛒 Lista della spesa per la {decade} generata con {len(items)} prodotti, totale: {total_cost:.2f}€")
    debug_print(f"Totali per negozio: {items}")
    return items, shop_totals





# Mainpage, calcola il numero dei prodotti che sono da riordinare
def get_reorder_count_from_shopping_list():
    # Usa la funzione esistente per ottenere i dati della lista della spesa
    items, _ = get_shopping_list_data()  # Considera la prima settimana del mese
    return len(items)  # Restituisce il numero totale di prodotti

# Mainpage, calcola il costo totale dei prodotti da riordinare
def get_reorder_total_cost():
    # Usa la funzione esistente per ottenere i dati della lista della spesa
    items, _ = get_shopping_list_data()  # Considera la prima settimana del mese
    total_cost = 0

    # Calcola il costo totale
    for item in items:
        total_cost += item["quantity_to_buy"] * item["price"]  # Prezzo totale per il prodotto

    return round(total_cost, 2)  # Arrotonda a due decimali

def get_suggested_products():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            pd.barcode,
            pd.name AS product_name,
            tf.quantity,
            i.min_quantity,
            i.security_quantity,
            i.reorder_point,
            i.mean_usage_time,
            pd.shop
        FROM product_settings i
        JOIN product_dim pd ON i.barcode = pd.barcode
        JOIN transaction_fact tf ON i.barcode = tf.barcode
        WHERE pd.name NOT IN (
            SELECT product_name FROM shopping_list
        )
        GROUP BY i.barcode
    """)

    rows = cursor.fetchall()
    conn.close()

    suggested = []
    for row in rows:
        motivo = None

        quantity = row["quantity"]
        min_q = row["min_quantity"]
        sec_q = row["security_quantity"]
        reorder_p = row["reorder_point"]
        usage_time = row["mean_usage_time"]

        if min_q is not None and min_q != '' and quantity < min_q:
            motivo = "Sotto quantità minima"
        elif usage_time is not None and usage_time != '' and float(usage_time) < 10:
            motivo = "Consumo frequente"
        elif sec_q is not None and sec_q != '' and quantity < sec_q:
            motivo = "Sotto scorta"
        elif reorder_p is not None and reorder_p != '' and quantity < reorder_p:
            motivo = "Vicino al punto di riordino"

        if motivo:
            suggested.append({
                "barcode": row["barcode"],
                "product_name": row["product_name"],
                "quantity": quantity,
                "min_quantity": min_q,
                "shop": row["shop"],
                "reason": motivo
            })

    return suggested

# Funzione per processare la coda della lista della spesa
def process_shopping_queue():
    debug_print("Processo la coda della lista della spesa...")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shopping_queue ORDER BY id ASC")
    rows = cursor.fetchall()

    debug_print(f"Trovate {len(rows)} righe nella coda della lista della spesa.")

    for row in rows:
        queue_id = row[0]
        product_name = row[1]
        quantity = row[2]
        price = row[3]
        expiry = row[4]
        shop = row[5]
        ins_date = row[6]

        debug_print(f"[INFO] Elaboro riga {queue_id}: {product_name}, Quantità: {quantity}, Prezzo: {price}, Scadenza: {expiry}, Negozio: {shop}")

        # Lookup in product_dim
        product_name_trimmed = product_name.strip()
        cursor.execute("SELECT id, barcode FROM product_dim WHERE TRIM(name) = ?", (product_name_trimmed,))
        result = cursor.fetchone()

        if not result:
            debug_print(f"[WARNING] Prodotto non trovato in product_dim: {product_name}. Riga ignorata.")
            continue

        product_key, barcode = result

        # Inserimento in transaction_fact
        cursor.execute("""
            INSERT INTO transaction_fact (
                product_key, barcode, price, quantity, consumed_quantity, ins_date,
                consume_date, expiry_date, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_key,
            barcode,
            price,
            quantity,
            0,
            ins_date,
            None,
            expiry,
            "in stock"
        ))

        # Rimuove dalla coda
        cursor.execute("DELETE FROM shopping_queue WHERE id = ?", (queue_id,))
        print(f"[INFO] Riga {queue_id} processata e rimossa dalla coda.")

        # Rimuove dalla lista della spesa
        cursor.execute("DELETE FROM shopping_list WHERE barcode = ?", (barcode,))
        print(f"[INFO] Prodotto {product_name} rimosso dalla lista della spesa.")

        # Aggiorna expenses_fact
        selected_decade = get_current_decade()
        amount = round(float(price) * int(quantity), 2)
        upsert_expense(cursor, ins_date, selected_decade, shop, amount)

    # Esegui commit e chiudi connessione **una volta sola**
    conn.commit()
    conn.close()

  