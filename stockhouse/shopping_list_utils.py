from datetime import datetime, timedelta
import sqlite3
from stockhouse.app_code.models import get_week_date_range
from config import Config  # usa il path corretto se è diverso
from stockhouse.utils import debug_print



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


# calcola_budget_settimanale per la spesa settimanale
def calcola_budget_settimanale(week_number, budget_mensile, spese_settimanali, settimana_reintegro):
    """
    Calcola il budget disponibile per la settimana corrente.
    
    Args:
        week_number (int): Numero della settimana attuale.
        budget_mensile (float): Budget totale mensile.
        spese_settimanali (dict): Dizionario con chiave=numero settimana, valore=spesa effettuata.
        settimana_reintegro (int): Settimana scelta per il reintegro del magazzino (es: quella con giorno >= 25).

    Returns:
        float: Budget disponibile per questa settimana.
    """

    # Parametri fissi configurabili
    quota_reintegro = 0.40  # 40% del budget se è settimana reintegro
    settimane_totali = 4

    spesa_totale_finora = sum(spese_settimanali.get(w, 0) for w in range(1, week_number))

    # Calcolo quota residua disponibile
    budget_residuo = budget_mensile - spesa_totale_finora

    # Se siamo nella settimana di reintegro
    if week_number == settimana_reintegro:
        budget_settimanale = budget_mensile * quota_reintegro
    else:
        # Distribuisci il resto del budget sulle settimane rimanenti (inclusa questa)
        settimane_rimanenti = settimane_totali - (week_number - 1)
        budget_settimanale = budget_residuo / max(settimane_rimanenti, 1)

    return round(budget_settimanale, 2)


# Funzioni utili per la gestione settimanale della lista della spesa

def is_last_week_with_25(week_number):

    start_date, end_date = get_week_date_range(week_number)
    return any(day >= 25 for day in range(start_date.day, end_date.day + 1))


def get_week_with_day_over_25():
    today = datetime.today()
    month = today.month
    num = 1
    while True:
        start_date, end_date = get_week_date_range(num)
        if start_date.month != month:
            break
        if any(day >= 25 for day in range(start_date.day, end_date.day + 1)):
            return num
        num += 1
    return None

def get_budget_info():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT budget, budget_ins_date FROM budget_config ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        return float(row['budget']), row['budget_ins_date']
    else:
        return 0, None
    

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


# Funzione per generare la lista della spesa mensile
def generate_monthly_shopping_list():
    today = datetime.today().date()
    current_month = today.strftime("%Y-%m")
    debug_print(f"Generazione lista spesa mensile per: {current_month}")

    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Controlla se la lista è già stata generata per questo mese
    cursor.execute("""
        SELECT COUNT(*) as count FROM shopping_list
        WHERE strftime('%Y-%m', insert_date) = ?
    """, (current_month,))
    result = cursor.fetchone()

    if result['count'] > 0:
        debug_print("La lista per questo mese è già stata generata. Nessuna azione necessaria.")
        conn.close()
        return

    debug_print("Nessuna lista trovata per il mese corrente. Procedo con la generazione...")

    for week_number in range(1, 5):
        is_restock_week = (week_number == 4)
        items, _ = get_shopping_list_data(
            week_number=week_number,
            is_restock_week=is_restock_week,
            save_to_db=True,
            conn=conn,
            cursor=cursor
        )
        debug_print(f"Lista spesa per la settimana {week_number}: {len(items)} prodotti")
        
        for item in items:
            cursor.execute("""
                INSERT INTO shopping_list (
                    barcode, product_name, quantity_to_buy,
                    shop, reason, price, week_number, insert_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["barcode"],
                item["product_name"],
                item["quantity_to_buy"],
                item["shop"],
                item["reason"],
                item["price"] or 0,
                week_number,
                today
            ))
        debug_print(f"✔️ Inseriti {len(items)} prodotti per la settimana {week_number} (Restock: {is_restock_week})")

    conn.commit()
    conn.close()
    debug_print("✅ Lista spesa mensile completata con successo.")



def safe_int(value):
    try:
        if value is None or str(value).strip() == '':
            return None
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None





# Mainpage, calcola la lista della spesa della settimana corrente
def get_shopping_list_data(week_number, is_restock_week=False, save_to_db=False,  conn=None, cursor=None):
 
 
    if conn is None or cursor is None:
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        external_connection = False
    else:
        external_connection = True
 
    
    debug_print(f"get_shopping_list_data - week_number: {week_number}, is_restock_week: {is_restock_week}")

    if save_to_db:
        # Cancella solo i dati della settimana corrente
        cursor.execute("DELETE FROM shopping_list WHERE week_number = ?", (week_number,))
        conn.commit()

    debug_print(f"get_shopping_list_data - Numero settimana corrente: {week_number}")
    debug_print(f"is_restock_week: {is_restock_week}")

    if is_restock_week:
        query = """
            SELECT 
                i.product_key, 
                i.barcode, 
                MAX(tf.quantity) as quantity,
                i.min_quantity, 
                i.max_quantity, 
                i.security_quantity, 
                i.reorder_point, 
                i.mean_usage_time, 
                i.reorder_frequency,
                pd.name,
                pd.shop,
                tf.price,
                totals.tot
            FROM inventory i
            JOIN product_dim pd ON i.barcode = pd.barcode
            JOIN transaction_fact tf ON i.barcode = tf.barcode
            JOIN (
                SELECT barcode, SUM(quantity) AS tot
                FROM transaction_fact
                GROUP BY barcode
            ) AS totals ON i.barcode = totals.barcode
            WHERE  
                (i.reorder_point IS NOT NULL AND i.reorder_point > 0)
                AND (
                    COALESCE(NULLIF(i.reorder_frequency, ''), i.mean_usage_time) >= 30 
                    OR totals.tot < i.security_quantity 
                    OR totals.tot < i.reorder_point 
                ) 
            GROUP BY i.barcode
        """
    else:
        query = """
            SELECT 
                i.product_key, 
                i.barcode, 
                MAX(tf.quantity) as quantity,
                i.min_quantity, 
                i.max_quantity, 
                i.security_quantity,
                i.reorder_point,
                i.mean_usage_time,
                pd.name,
                pd.shop,
                tf.price
            FROM inventory i
            JOIN transaction_fact tf ON i.barcode = tf.barcode
            JOIN product_dim pd ON i.barcode = pd.barcode
            WHERE 
                tf.quantity = 0 
                OR tf.quantity < i.min_quantity
                OR COALESCE(NULLIF(i.reorder_frequency, ''), i.mean_usage_time) < 15
            GROUP BY i.barcode
        """

    cursor.execute(query)
    rows = cursor.fetchall()
    if not save_to_db:
        conn.close()

    items = []
    shop_totals = {}

    for row in rows:
        if (row['quantity'] is not None and row['max_quantity'] is not None and row['max_quantity'] != ''):
            quantity_to_buy = max(row['max_quantity'] - row['quantity'], 1)
        else:
            quantity_to_buy = 1

        quantity = safe_int(row['quantity'])
        security_quantity = safe_int(row['security_quantity'])
        reorder_point = safe_int(row['reorder_point'])
        mean_usage_time = safe_int(row['mean_usage_time'])

        if is_restock_week:
            # Prima converti i valori
            motivo = "Riordino programmato"
            if quantity is not None and security_quantity is not None and quantity < security_quantity:
                motivo = "Sotto scorta"
            elif quantity is not None and reorder_point is not None and quantity < reorder_point:
                motivo = "Vicino al punto di riordino"
            elif mean_usage_time is not None and mean_usage_time > 15:
                motivo = "Consumo rapido"
        else:
            motivo = "Esaurito" if quantity == 0 else "Sotto quantità minima"

        item = {
            "barcode": row['barcode'],
            "product_name": row['name'],
            "quantity_to_buy": quantity_to_buy,
            "shop": row['shop'],
            "reason": motivo,
            "price": row['price'] or 0,
            "week_number": week_number
        }
        items.append(item)

        if item["shop"]:
            shop_totals.setdefault(item["shop"], 0)
            shop_totals[item["shop"]] += quantity_to_buy * item["price"]

    if save_to_db:
        for item in items:
            cursor.execute("""
                INSERT INTO shopping_list (barcode, product_name, quantity_to_buy, shop, reason, price, week_number, insert_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'))
            """, (
                item["barcode"],
                item["product_name"],
                item["quantity_to_buy"],
                item["shop"],
                item["reason"],
                item["price"],
                week_number
            ))
        conn.commit()

        if not external_connection:
            conn.close()

    return items, shop_totals





# Mainpage, calcola il numero dei prodotti che sono da riordinare
def get_reorder_count_from_shopping_list():
    # Usa la funzione esistente per ottenere i dati della lista della spesa
    items, _ = get_shopping_list_data(get_current_week())  # Considera la prima settimana del mese
    return len(items)  # Restituisce il numero totale di prodotti

# Mainpage, calcola il costo totale dei prodotti da riordinare
def get_reorder_total_cost():
    # Usa la funzione esistente per ottenere i dati della lista della spesa
    items, _ = get_shopping_list_data(get_current_week())  # Considera la prima settimana del mese
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
        FROM inventory i
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
