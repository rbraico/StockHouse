FROM python:3.11-slim

# Imposta la directory di lavoro nel container
WORKDIR /StockHouse

# Copia tutto il codice dell'app nel container
COPY . .

# Aggiorna il sistema e installa Tesseract + lingue necessarie
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng tesseract-ocr-nld && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Imposta la variabile TESSDATA_PREFIX per far trovare a Tesseract i traineddata
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# Definisci le variabili d'ambiente per Flask e DB
ENV FLASK_APP=stockhouse.app_code:create_app
ENV DB_PATH=/config/sqlite_db/stockhouse.db

# Espone la porta 9192
EXPOSE 9192

# Comando per avviare Flask
CMD ["flask", "run", "--host=0.0.0.0", "--port=9192"]