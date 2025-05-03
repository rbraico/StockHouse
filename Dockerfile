FROM python:3.11-slim

# Imposta la directory di lavoro nel container
WORKDIR /StockHouse

# Copia tutto il codice dell'app nel container
COPY . .

# Aggiorna il sistema e installa le dipendenze
RUN apt-get update && apt-get upgrade -y && \
    pip install --no-cache-dir -r requirements.txt

# Definisci la variabile d'ambiente per Flask
ENV FLASK_APP=stockhouse.app_code:create_app
ENV DB_PATH=/config/sqlite_db/stockhouse.db

# Espone la porta 9192
EXPOSE 9192

# Comando per avviare Flask
CMD ["flask", "run", "--host=0.0.0.0", "--port=9192"]