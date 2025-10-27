from datetime import datetime, timedelta, date
import sqlite3
from stockhouse.app_code.models import get_week_date_range, recalculate_seasonal_priorities, upsert_expense, lookup_products_by_name, upsert_transaction_fact
from config import Config  # usa il path corretto se è diverso
from stockhouse.utils import debug_print
import calendar
from rapidfuzz import process, fuzz

import json
import re

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

# Funzione per ottenere l'intervallo di date della decade corrente
def get_decade_range(current_date=None):
    if current_date is None:
        current_date = date.today()

    day = current_date.day
    year = current_date.year
    month = current_date.month

    if day <= 10:
        start_decade_date = date(year, month, 1)
        end_decade_date = date(year, month, 10)
    elif day <= 20:
        start_decade_date = date(year, month, 11)
        end_decade_date = date(year, month, 20)
    else:
        start_decade_date = date(year, month, 21)
        # Prende ultimo giorno del mese
        last_day = calendar.monthrange(year, month)[1]
        end_decade_date = date(year, month, last_day)

    return start_decade_date, end_decade_date


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


# Funzione per ottenere il budget corrente per la decade specificata
def get_budget_decade_corrente(decade=None):

    debug_print(f"📆 get_budget_decade_corrente: Decade richiesta: {decade}")
    
    # Recupera le info di budget dal DB
    budget_info = get_budget_info()
    budget_del_mese = float(budget_info['budget']) 
    debug_print(f"💰 Budget totale: {budget_del_mese:.2f}€")

    # Calcola il budget previsto per ogni decade
    budget_per_decade = {
        "D1": budget_del_mese * float(budget_info['decade1']) / 100,
        "D2": budget_del_mese * float(budget_info['decade2']) / 100,
        "D3": budget_del_mese * float(budget_info['decade3']) / 100
    }

    # Recupera la spesa effettiva per ogni decade
    spesa_decade = get_spesa_per_decade()
    spesa_per_decade = {
        "D1": spesa_decade[0],
        "D2": spesa_decade[1],
        "D3": spesa_decade[2]
    }

    # Calcolo del budget corrente con taglio prudenziale del 20%
    budget_corrente = budget_per_decade[decade] #* 0.80
    spesa_corrente = spesa_per_decade[decade]

    # Calcolo del bilancio precedente solo per D2 e D3
    bilancio_precedente = 0
    if decade == "D2":
        bilancio_precedente = budget_per_decade["D1"] - spesa_per_decade["D1"]
        budget_corrente = budget_per_decade[decade] + bilancio_precedente
    elif decade == "D3":
        bilancio_precedente = budget_per_decade["D2"] + (budget_per_decade["D1"] - spesa_per_decade["D1"]) - spesa_per_decade["D2"]
        budget_corrente = budget_per_decade[decade] + bilancio_precedente

    debug_print(f"📆 get_budget_per_decade_corrente: Budget corrente per {decade}: {budget_corrente:.2f}€ bilancio precedente: {bilancio_precedente:.2f}€ ")
    # Budget disponibile = budget corrente - spesa corrente + eventuale avanzo precedente
    budget_disponibile = budget_corrente - spesa_corrente

    debug_print(
        f"📆 get_budget_per_decade_corrente: Decade: {decade}, "
        f"Budget corrente (80%): {budget_corrente:.2f}, "
        f"Spesa corrente: {spesa_corrente:.2f}, "
        f"Bilancio precedente: {bilancio_precedente:.2f}, "
        f"➡️ Budget disponibile: {budget_disponibile:.2f}"
    )

    return budget_corrente, budget_disponibile



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


# Funzione per calcolare la priorità personalizzata
def calcola_priority_personalizzata(
    necessity_level,
    quantity,
    reorder_point,
    min_q,
    category,
    offerta,
    seasonal_priority=None  # solo per prodotti stagionali
):
    # Step 1: Categorie prioritarie assolute
    categorie_prioritarie = ["Primo soccorso", "Igiene personale", "Prodotti per la casa"]
    if category in categorie_prioritarie:
        return 1

    # Step 5: Prodotti stagionali
    if necessity_level == "Stagionale" and seasonal_priority is not None:
        if seasonal_priority == 1:  # di stagione
            if offerta == 1:
                return 1
            elif quantity <= min_q:
                return 2
            elif quantity <= reorder_point:
                return 3
        elif seasonal_priority == 2:  # stagione adiacente
            if offerta == 1:
                return 4
            elif quantity <= min_q:
                return 5
            elif quantity <= reorder_point:
                return 6
        elif seasonal_priority == 3:  # fuori stagione
            return 10

    # Step 2: Necessità "Indispensabile"
    if necessity_level == "Indispensabile":
        if offerta == 1:
            return 1
        elif quantity <= min_q:
            return 2
        elif quantity <= reorder_point:
            return 3

    # Step 3: Necessità "Utili"
    if necessity_level == "Utile":
        if offerta == 1:
            return 4
        elif quantity <= min_q:
            return 5
        elif quantity <= reorder_point:
            return 6

    # Step 4: Necessità "Occasionale"
    if necessity_level == "Occasionale":
        if offerta == 1:
            return 7
        elif quantity <= min_q:
            return 8
        elif quantity <= reorder_point:
            return 9

    # Fallback finale
    return 10



# Funzione per ottenere i dati della lista della spesa
def get_shopping_list_data(save_to_db=False, conn=None, cursor=None, decade=None):
 
    
    debug_print("get_shopping_list_data, save_to_db:", save_to_db, "decade:", decade)

    external_connection = False
    if conn is None or cursor is None:
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        external_connection = True

    # Calcola l'intervallo di date della decade corrente
    start_decade, end_decade = get_decade_range()

    # Usa decade passata oppure calcola quella corrente
    decade = decade or get_current_decade()
    debug_print(f"📆 Decade corrente/elaborata: {decade}")

    # Recupera le info di budget dal DB
    budget_corrente, budget_disponibile = get_budget_decade_corrente(decade)

    debug_print(f"💰 Budget corrente per la {decade}: {budget_corrente:.2f}")

    debug_print(f"💰 Budget disponibile per la {decade}: {budget_disponibile:.2f}")

    main_query = """
        SELECT 
            i.barcode,
            COALESCE(stock.total_quantity, 0) AS quantity,
            i.reorder_point, i.min_quantity, i.max_quantity, i.security_quantity,
            pd.name, pd.shop, tf.price, pd.category,
            i.necessity_level, i.priority_level,
            MAX(tf.ins_date) as ins_date
        FROM product_settings i
        LEFT JOIN (
            SELECT 
                barcode,
                SUM(quantity) - COALESCE(SUM(consumed_quantity), 0) AS total_quantity
            FROM transaction_fact
            GROUP BY barcode
        ) AS stock ON i.barcode = stock.barcode
        LEFT JOIN transaction_fact tf ON i.barcode = tf.barcode
        LEFT JOIN product_dim pd ON i.barcode = pd.barcode
        WHERE i.max_quantity > 0
        AND (pd.category LIKE '%Alimenti freschi' OR pd.item LIKE '%Alimenti Congelati')
        GROUP BY i.barcode
        HAVING (
            (i.necessity_level = 'Indispensabile' AND COALESCE(stock.total_quantity, 0) <= i.reorder_point)
            OR
            (pd.category LIKE '%Alimenti freschi' AND COALESCE(stock.total_quantity, 0) < i.min_quantity)
                OR
            (pd.category LIKE '%Alimenti Congelati' AND COALESCE(stock.total_quantity, 0) < i.min_quantity)
        )
        ORDER BY i.priority_level ASC, ins_date ASC, tf.price ASC;
        """
    cursor.execute(main_query)
    rows = cursor.fetchall()


    expiring_query = """
        SELECT dim.barcode,
            SUM(tf.quantity) AS quantity,
            inv.reorder_point,
            inv.min_quantity,
            inv.max_quantity,
            inv.security_quantity,
            dim.name,
            dim.shop,
            tf.price,
            dim.category,
            inv.necessity_level,
            1 AS priority_level,
            MIN(tf.ins_date) as ins_date
        FROM transaction_fact tf
        INNER JOIN product_dim dim ON dim.id = tf.product_key
        JOIN product_settings inv ON tf.barcode = inv.barcode
        WHERE tf.expiry_date IS NOT NULL 
        AND tf.status = "in stock"
        AND tf.expiry_date BETWEEN ? AND ?
        GROUP BY tf.barcode  
        ORDER BY tf.expiry_date ASC
   """


    # prodotti con scorte critiche
    critical_stock_query = """
        SELECT  
            dim.barcode,
            SUM(tf.quantity) AS quantity,
            inv.reorder_point,
            inv.min_quantity,
            inv.max_quantity,
            inv.security_quantity,
            dim.name,
            dim.shop,
            tf.price,
            dim.category,
            inv.necessity_level,
            1 AS priority_level,
            MIN(tf.ins_date) as ins_date
        FROM transaction_fact tf
        JOIN product_dim dim ON tf.barcode = dim.barcode
        JOIN product_settings inv ON tf.barcode = inv.barcode
        GROUP BY tf.barcode
        HAVING SUM(tf.quantity) < inv.security_quantity;
    """

    if decade == "D3":
        # Prima prendi i prodotti speciali D3

        # seleziona i prodotti che stanno scadendo
        cursor.execute(expiring_query, (start_decade.strftime("%Y-%m-%d"), end_decade.strftime("%Y-%m-%d")))
        rows = cursor.fetchall()
        debug_print(f"Prodotti in scadenza trovati: {len(rows)}")
        
        # aggiunge i prodotti con scorte critiche
        cursor.execute(critical_stock_query)
        rows_critical_stock = cursor.fetchall()
        rows.extend(rows_critical_stock)
        debug_print(f"Prodotti con scorte critiche trovati: {len(rows_critical_stock)}")

        # Poi prendi i prodotti standard
        cursor.execute(main_query)
        main_rows = cursor.fetchall()
        rows.extend(main_rows)
        debug_print(f"Prodotti standard trovati: {len(main_rows)}")

    else:
        # Solo prodotti standard
        cursor.execute(main_query)
        rows = cursor.fetchall()

    # Deduplicazione: tieni la prima occorrenza per barcode
    unique_rows = {}
    deduped_rows = []
    for row in rows:
        barcode = row["barcode"]
        if barcode not in unique_rows:
            unique_rows[barcode] = True
            deduped_rows.append(row)

    rows = deduped_rows


    debug_print(f"Query eseguita, trovati {len(rows)} prodotti per la {decade}, save_to_db: {save_to_db}")

    # Converti in dict
    rows = [dict(r) for r in rows]

    # 🔹 Calcola PRIORITÀ personalizzata prima del ciclo
    for row in rows:
        quantity = parse_quantity(row["quantity"])
        min_q = parse_quantity(row["min_quantity"])
        reorder_point = parse_quantity(row["reorder_point"])
        necessity_level = row["necessity_level"]
        category = row["category"]
        offerta = 0
        seasonal_priority = row["priority_level"]
        row['order_by_list'] = calcola_priority_personalizzata(
            necessity_level, quantity, reorder_point, min_q, category, offerta, seasonal_priority
        )
        debug_print(f"Prodotto {row['name']}: order_by_list = {row['order_by_list']}")

    # 🔹 Ordina le righe
    rows.sort(key=lambda r: r['order_by_list'])


    items = []
    shop_totals = {}
    total_cost = 0

    for row in rows:
        barcode = row["barcode"]
        product_name = row["name"]
        shop = row["shop"]
        price = row["price"] or 0

        category = row["category"]
        quantity = parse_quantity(row["quantity"])
        max_q = parse_quantity(row["max_quantity"])
        min_q = parse_quantity(row["min_quantity"])
        sec_q = parse_quantity(row["security_quantity"])
        reorder_point = parse_quantity(row["reorder_point"])
        necessity_level = row["necessity_level"]
        quantity_to_buy = 1
        reason = ""
        seasonal_priority = row["priority_level"]
        offerta=0

        if "Alimenti freschi" in category:
            quantity_to_buy = max(max_q - quantity, 1)
            reason = "Acquisto abituale alimento fresco"
        elif necessity_level == "Indispensabile" and quantity <= sec_q:
            if decade == "D3":
                quantity_to_buy = max(max_q - quantity, 1)
                reason = "Reintegro scorte"
            else:
                quantity_to_buy = max(reorder_point - quantity, 1)
                reason = "Sotto scorta"
            debug_print(f"Prodotto {product_name} è Indispensabile, sotto scorta: {quantity} < {sec_q}")
        elif max_q > quantity and quantity <= reorder_point:
            quantity_to_buy = max(max_q - quantity, 1)
            reason = "Reintegro scorte"
            debug_print(f"Prodotto {product_name} è in Reintegro scorte: {quantity} <= {reorder_point}")


        
        product_cost = quantity_to_buy * price
        total_cost += product_cost

        debug_print(f"Hei Budget disponibie: {budget_disponibile}, Prodotto: {product_name}, Quantità da acquistare: {quantity_to_buy}, Prezzo unitario: {price:.2f}€, Costo totale: {product_cost:.2f}€, Spesa corrente: {total_cost:.2f}€")

        # Se il prodotto rientra nel budeget, aggiorna il budget
        if product_cost <= budget_disponibile:
            within_budget = 1
            budget_disponibile = budget_disponibile - product_cost
        else:
            within_budget = 0


        debug_print(f"Prodotto: {product_name}, within_budget: {within_budget},  Quantità da acquistare: {quantity_to_buy}, Ragione: {reason}, Prezzo unitario: {price:.2f}€, Costo totale: {product_cost:.2f}€, Budget rimanente: {budget_disponibile - total_cost:.2f}€")

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
        # 1️⃣ Pulisce solo i record ATTIVI (within_budget=1) di decadi vecchie, escludendo i manuali
        cursor.execute("""
            DELETE FROM shopping_list
            WHERE decade_number != ?

        """, (decade,))

        # 2️⃣ Inserisce/aggiorna in un colpo solo
        for item in items:
            # Salta se il calcolo dice che non è nel budget
            if item.get("within_budget", 0) == 0:
                continue

            cursor.execute("""
                INSERT INTO shopping_list (
                    barcode, product_name, quantity_to_buy,
                    shop, reason, price, decade_number, insert_date, within_budget
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'), ?)
                ON CONFLICT(barcode, decade_number) DO UPDATE SET
                    product_name = excluded.product_name,
                    quantity_to_buy = excluded.quantity_to_buy,
                    shop = excluded.shop,
                    reason = excluded.reason,
                    price = excluded.price,
                    insert_date = DATE('now'),
                    within_budget = CASE
                        WHEN shopping_list.within_budget = 0 THEN 0  -- Rispetta la rimozione manuale
                        ELSE excluded.within_budget
                    END
            """, (
                item["barcode"], item["product_name"], item["quantity_to_buy"],
                item["shop"], item["reason"], item["price"], decade,
                item["within_budget"]
            ))

        conn.commit()

    # Recupera tutti gli elementi della lista della spesa
    cursor.execute("SELECT * FROM shopping_list WHERE within_budget = 1")
    items = cursor.fetchall() 

    shop_totals = {}
    for item in items:
        #debug_print(f"Elaboro prodotto: {item['product_name']}, Ragione: {item['reason']}, Quantità da acquistare: {item['quantity_to_buy']}, Prezzo unitario: {item['price']:.2f}€")

        shop = item["shop"]  # oppure item['shop'] se items è una lista di dict
        product_cost = item["price"] * item["quantity_to_buy"]
        if shop:
            shop_totals.setdefault(shop, 0)
            shop_totals[shop] += product_cost

    # Ordina per negozio
    shop_totals = dict(sorted(shop_totals.items(), key=lambda x: x[0].lower()))        

    if external_connection:
        conn.close()

    # Se il refresh è stato richiesto, aggiorna lo stato
    set_refresh_needed(False, decade)

    debug_print(f"🛒 Lista della spesa per la {decade} generata con {len(items)} prodotti, totale: {total_cost:.2f}€")
    #debug_print(f"Totali per negozio: {items}")
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

# Funzione per ottenere i prodotti suggeriti non ancora nella lista della spesa
def get_suggested_products():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            pd.barcode,
            pd.name AS product_name,
            pd.shop,
            pd.image,
            pd.item,
            tf.price,
            COALESCE(sl.quantity_to_buy, 1) AS quantity
        FROM product_dim pd
        LEFT JOIN transaction_fact tf ON pd.barcode = tf.barcode
        LEFT JOIN shopping_list sl ON pd.barcode = sl.barcode
        GROUP BY pd.barcode
        ORDER BY pd.name ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    suggested = []
    for row in rows:
        suggested.append({
            "barcode": row["barcode"],
            "product_name": row["product_name"],
            "shop": row["shop"],
            "image_url": row["image"],
            "item_type": row["item"],
            "price": row["price"],
            "quantity": row["quantity"]  # ← ora incluso direttamente dalla query
        })

    return suggested


import threading
# Funzione per testare il thread alla chiusura della pagina shopping list per il riordino dei prodotti secondo lo schema del supermercato
def trigger_thread_on_exit():
    """
    Funzione minimale per testare il thread alla chiusura della pagina.
    Per ora stampa solo un messaggio.
    """
    def task():
        print("✅ Ok, thread selezionato e in esecuzione")
    
    threading.Thread(target=task, daemon=True).start()



# Funzione per processare la coda della lista della spesa
def process_shopping_queue():
    debug_print("Processo la coda della lista della spesa...")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shopping_queue ORDER BY id ASC")
    rows = cursor.fetchall()

    debug_print(f"Trovate {len(rows)} righe nella coda della lista della spesa. ")

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
        amount = round(float(price) * int(quantity),  2)
        
        #upsert_expense(cursor, ins_date, selected_decade, shop, amount)

    # Esegui commit e chiudi connessione **una volta sola**
    conn.commit()
    conn.close()

# Nuove funzioni per il refresh della shopping list
def set_refresh_needed(value=True, current_decade=None):
    debug_print(f"set_refresh_needed: Imposto refresh_needed a {value}")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_state (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, ("shopping_list_refresh_needed", '1' if value else '0'))
    conn.commit()
    conn.close()

def is_refresh_needed():
    debug_print("is_refresh_needed: Controllo se il refresh è necessario")
    
    current_decade = get_current_decade()
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Legge il valore e la decade salvata
    cursor.execute("""
        SELECT value, decade 
        FROM system_state 
        WHERE key = ?
    """, ("shopping_list_refresh_needed",))
    result = cursor.fetchone()

    saved_value = result[0] if result else '0'
    saved_decade = result[1] if result else None

    debug_print(f"Valore salvato: {saved_value}, Decade salvata: {saved_decade}, Decade corrente: {current_decade}")

    refresh_needed = False

    # Caso 1: flag esplicito
    if saved_value == '1':
        debug_print("Refresh necessario: flag value=1")
        refresh_needed = True

    # Caso 2: cambio decade
    elif saved_decade != current_decade:
        debug_print("Refresh necessario: cambio decade")

        # Se è cambiata la decade, forza il refresh e ricalcola le priorità stagionali
        recalculate_seasonal_priorities ()

        refresh_needed = True
        # Aggiorna la decade salvata
        cursor.execute("""
            INSERT INTO system_state(key, value, decade)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET decade=excluded.decade
        """, ("shopping_list_refresh_needed", saved_value, current_decade))
        conn.commit()

    # Caso 3: shopping_list vuota per la decade corrente
    else:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM shopping_list 
            WHERE decade_number = ?
        """, (current_decade,))
        count = cursor.fetchone()[0]
        if count == 0:
            debug_print("Refresh necessario: shopping_list vuota per la decade corrente")
            refresh_needed = True

    conn.close()
    debug_print(f"Risultato finale is_refresh_needed: {refresh_needed}")
    return refresh_needed



# Funzione per rimuovere prodotti dalla lista della spesa - setta within_budget a 0
# saranno cancellati definitivamente la prossima decade
def remove_from_shopping_lst(barcodes):
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        for bc in barcodes:
            cursor.execute("UPDATE shopping_list SET within_budget = 0 WHERE barcode = ?", (bc,))
        conn.commit()
    finally:
        conn.close()


def normalize_text(text):
    # Funzione base di normalizzazione: minuscole, togli spazi
    return text.lower().replace(" ", "")


def get_aliases_from_db(shop=None):

    debug_print(f"Recupero alias prodotti dal database per il negozio: {shop if shop else 'tutti'}")
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    if shop:
        cursor.execute("SELECT normalized_alias, product_id FROM product_alias WHERE shop = ?", (shop,))
    else:
        cursor.execute("SELECT normalized_alias, product_id FROM product_alias")
    rows = cursor.fetchall()
    conn.close()
    return rows


def fuzzy_match_product(name, aliases):
    norm_name = normalize_text(name)
    choices = [a[0] for a in aliases]  # normalized_alias
    # Cerca miglior match
    match = process.extractOne(norm_name, choices, scorer=fuzz.ratio)
    if match:
        matched_name, score, index = match
        debug_print(f"Fuzzy match trovato: {matched_name} con punteggio {score} per '{norm_name}'")

        product_id = aliases[index][1]
        confidence = score / 100.0
        return product_id, confidence, matched_name
    return None, 0.0        



def insert_unknown_product(
    shop_name,
    raw_name,
    matched_product_id=None,
    normalized_name="",
    note="",
    traduzione_italiano=None,
    quantita=None,
    prezzo_unitario=None,
    prezzo_totale=None
):
    """
    Inserisce un prodotto non riconosciuto nella tabella 'unknown_products'.
    
    Parametri:
    - shop_name (str): Nome del negozio dove è stato rilevato il prodotto.
    - raw_name (str): Nome originale grezzo del prodotto rilevato dallo scontrino.
    - normalized_name (str): Nome normalizzato (es. minuscole, senza spazi) per matching.
    - matched_product_id (int|None): ID prodotto suggerito se il matching è riuscito.
    - note (str): Note aggiuntive, ad esempio livello di confidenza basso.
    - nome (str|None): Nome "pulito" del prodotto (es. tradotto o corretto).
    - traduzione_italiano (str|None): Traduzione in italiano del nome prodotto.
    - quantita (int|None): Quantità acquistata.
    - prezzo_unitario (float|None): Prezzo unitario. Se assente e quantità = 1, viene impostato uguale al prezzo totale.
    - prezzo_totale (float|None): Prezzo totale del prodotto.

    Comportamento speciale:
    Se la quantità è 1 e il prezzo unitario è mancante o zero,
    la funzione imposta prezzo_unitario uguale a prezzo_totale per evitare dati mancanti.

    Salva tutte queste informazioni nella tabella 'unknown_products'.
    """
    
    debug_print(f"Inserimento prodotto sconosciuto: {raw_name}, Normalizzato: {normalized_name}, traduzione: {traduzione_italiano}, ID suggerito: {matched_product_id}, Quantità: {quantita}, Prezzo unitario: {prezzo_unitario}, Prezzo totale: {prezzo_totale}")                                                                                                                     
    
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO unknown_products 
        (shop_name, raw_name, matched_product_id,  normalized_name,  traduzione_italiano, quantita, prezzo_unitario, prezzo_totale, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (shop_name, raw_name, matched_product_id, normalized_name, traduzione_italiano, quantita, prezzo_unitario, prezzo_totale, note))
    conn.commit()
    conn.close()





def aggiorna_tabella_shopping_list(lista_ordinata):
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()

    # Cancella tutti i record esistenti
    cursor.execute("DELETE FROM shopping_list")

    # Query di inserimento
    insert_query = """
        INSERT INTO shopping_list (
            barcode, product_name, quantity_to_buy, shop,
            reason, price, decade_number, insert_date, within_budget
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # Inserisci ogni record ordinato
    for prodotto in lista_ordinata:
        cursor.execute(insert_query, (
            prodotto.get("barcode"),
            prodotto.get("product_name"),
            prodotto.get("quantity_to_buy"),
            prodotto.get("shop"),
            prodotto.get("reason"),
            prodotto.get("price"),
            prodotto.get("decade_number"),
            prodotto.get("insert_date"),
            prodotto.get("within_budget")
        ))

    # Salva e chiudi
    conn.commit()
    conn.close()
    print("✅ Tabella shopping_list aggiornata con successo.")



def ordina_lista_spesa(json_input):
    # Se json_input è una stringa, convertila in oggetto Python
    if isinstance(json_input, str):
        lista_spesa = json.loads(json_input)
    else:
        lista_spesa = json_input

    # Sequenza desiderata delle categorie
    ordine_categorie = [
        "🍝 Pasta", "🍎 Frutta", "🥦 Verdura", "🥐 Prodotti da forno", "🍞Pane",
        "🥩Carne", "🐟 Pesce", "🫒 Condimenti", "🍕Pizza", "🌾Cereali", "🧀Formaggi",
        "🍖Salumi", "🥫Conserve in scatola", "🫘Legumi", "🍵Infusi", "🥛Latte",
        "🍯Dolcificanti", "🌾Farine", "🥜 Frutta secca", "🍺Bevande", "🍰 Dolci",
        "🍧Gelati", "🪥Dentifricio", "🫧Sapone", "🧹Accessori per la pulizia"
    ]

    # Mappa di priorità
    priorita = {categoria: i for i, categoria in enumerate(ordine_categorie)}

    # Ordina la lista: se "item" è None o mancante, assegna priorità alta (999)
    lista_ordinata = sorted(
        lista_spesa,
        key=lambda x: priorita.get(x.get("item") or "", 999)
    )

    # Stampa per debug
    print(json.dumps(lista_ordinata, indent=4, ensure_ascii=False))

    return lista_ordinata


def finalizza_shopping_list():
    debug_print("Finalizza la shopping list ordinandola...")
    
    # Connessione al database
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # Esegui la SELECT completa
    cursor.execute("select distinct pd.item, sl.* from shopping_list sl left join product_dim pd on sl.barcode=pd.barcode")
    rows = cursor.fetchall()

    # Recupera i nomi delle colonne
    columns = [description[0] for description in cursor.description]

    # Costruisci la lista di dizionari
    shopping_data = [dict(zip(columns, row)) for row in rows]

    # Converti in JSON e stampa
    json_output = json.dumps(shopping_data, indent=2, ensure_ascii=False)
    debug_print("Shopping list fetched:", json_output)


    # Chiudi la connessione
    conn.close()

    lista_spesa = ordina_lista_spesa(json_output)
    aggiorna_tabella_shopping_list(lista_spesa)
    