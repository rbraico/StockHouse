from datetime import datetime, timedelta, date
import sqlite3
from stockhouse.app_code.models import get_week_date_range
from config import Config  # usa il path corretto se è diverso
from stockhouse.utils import debug_print



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


def format_decade_label(decade_number):
    labels = {
        1: "1ª Decade (1-10)",
        2: "2ª Decade (11-20)",
        3: "3ª Decade (21-31)"
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

    # Controlla se ci sono già dati per questo mese
    cursor.execute("""
        SELECT COUNT(*) as count FROM shopping_list
        WHERE strftime('%Y-%m', insert_date) = ?
    """, (current_month,))
    result = cursor.fetchone()

    if result['count'] > 0:
        debug_print("⚠️ La lista per questo mese è già stata generata. Nessuna azione necessaria.")
        conn.close()
        return

    debug_print("✅ Nessuna lista trovata per il mese corrente. Procedo con la generazione...")

    # Genera per ogni decade, passando il parametro
    for decade in ["D1", "D2", "D3"]:
        debug_print(f"Generazione lista per {decade}...")
        items, _ = get_shopping_list_data(save_to_db=True, conn=conn, cursor=cursor, decade=decade)
        debug_print(f"✔️ Inseriti {len(items)} prodotti per la {decade}")

    conn.commit()
    conn.close()
    debug_print("🎯 Lista spesa mensile completata con successo.")


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


    # deve chiamare update_inventory_advanced_options(barcode, product_type, seasons)

    external_connection = False
    if conn is None or cursor is None:
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        external_connection = True

    # Usa decade passata oppure calcola quella corrente
    decade = decade or get_current_decade()
    debug_print(f"📆 Decade corrente/elaborata: {decade}")

    # Recupera il budget totale dal DB
    cursor.execute("SELECT budget FROM budget_config LIMIT 1")
    row = cursor.fetchone()
    monthly_budget = row["budget"] if row else 0

    # Percentuali budget per decade
    if decade == "D1":
        budget = monthly_budget * 0.15
    elif decade == "D2":
        budget = monthly_budget * 0.30
    else:
        budget = monthly_budget * 0.55

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
                adv.product_type, adv.priority_level,
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
            JOIN inventory_advanced_options adv ON i.barcode = adv.barcode
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
            ORDER BY adv.priority_level ASC, tf.price ASC
        """
    elif decade == "D1": 
        # Prima decade: prodotti freschi e indispensabili
        query = """
            SELECT 
                i.barcode,
                stock.total_quantity AS quantity,
                i.reorder_point, i.min_quantity, i.max_quantity, i.security_quantity,
                pd.name, pd.shop, tf.price,
                adv.product_type, adv.priority_level
            FROM product_settings i
            JOIN(
                SELECT barcode, SUM(quantity) AS total_quantity
                FROM transaction_fact
                WHERE status = 'in stock'
                GROUP BY barcode
            ) AS stock ON i.barcode = stock.barcode
            JOIN transaction_fact tf ON i.barcode = tf.barcode
            JOIN product_dim pd ON i.barcode = pd.barcode
            JOIN inventory_advanced_options adv ON i.barcode = adv.barcode
            WHERE i.max_quantity > 0
            AND (pd.item LIKE '%Frutta' OR pd.item LIKE '%Verdura') -- prodotti freschi
            GROUP BY i.barcode
            HAVING (
                (adv.product_type = 'Indispensabile' AND stock.total_quantity <= i.security_quantity)
                OR
                (pd.category LIKE '%Alimenti freschi' AND stock.total_quantity < i.min_quantity)
            )
            ORDER BY adv.priority_level ASC, tf.price ASC
        """
    else:
        # Seconda decade: prodotti freschi e indispensabili e utilo avendo piu budget
        query = """
            SELECT
            i.barcode,
            stock.total_quantity AS quantity,
            i.reorder_point, i.min_quantity, i.max_quantity, i.security_quantity,
            pd.name, pd.shop, tf.price,
            adv.product_type, adv.priority_level
            FROM product_settings i
            JOIN (
            SELECT barcode, SUM(quantity) AS total_quantity
            FROM transaction_fact
            WHERE status = 'in stock'
            GROUP BY barcode
            ) AS stock ON i.barcode = stock.barcode
            JOIN transaction_fact tf ON i.barcode = tf.barcode
            JOIN product_dim pd ON i.barcode = pd.barcode
            JOIN inventory_advanced_options adv ON i.barcode = adv.barcode
            WHERE i.max_quantity > 0
            GROUP BY i.barcode
            HAVING (
            (adv.product_type = 'Indispensabile' AND stock.total_quantity <= i.reorder_point)
            OR
            (adv.product_type = 'Utile' AND stock.total_quantity < i.min_quantity)
            OR
            (pd.category LIKE "%Alimenti Freschi" AND stock.total_quantity < i.min_quantity)
            )
            ORDER BY adv.priority_level ASC, tf.price ASC;
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
        product_type = row["product_type"]
        quantity_to_buy = 1
        reason = ""

        if product_type == "Indispensabile" and quantity < sec_q:
            quantity_to_buy = max(sec_q - quantity, 1)
            reason = "Sotto scorta"
        elif product_type == "Fresco" and quantity < min_q:
            quantity_to_buy = max(min_q - quantity, 1)
            reason = "Da consumare"
        elif max_q > quantity and quantity <= reorder_point:
            quantity_to_buy = max(max_q - quantity, 1)
            reason = "Reintegro scorte"
  

        product_cost = quantity_to_buy * price
        if total_cost + product_cost > budget:
            debug_print("❌ Raggiunto il limite di budget")
            break

        total_cost += product_cost

        item = {
            "barcode": barcode,
            "product_name": product_name,
            "quantity_to_buy": quantity_to_buy,
            "shop": shop,
            "reason": reason,
            "price": price,
            "decade_number": decade
        }
        items.append(item)

        if shop:
            shop_totals.setdefault(shop, 0)
            shop_totals[shop] += product_cost

    debug_print("save_to_db, decade:", decade)

    if save_to_db:
        cursor.execute("DELETE FROM shopping_list WHERE decade_number = ?", (decade,))
        for item in items:
            cursor.execute("""
                INSERT INTO shopping_list (
                    barcode, product_name, quantity_to_buy,
                    shop, reason, price, decade_number, insert_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'))
            """, (
                item["barcode"], item["product_name"], item["quantity_to_buy"],
                item["shop"], item["reason"], item["price"], item["decade_number"]
            ))
        conn.commit()

    if external_connection:
        conn.close()

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
