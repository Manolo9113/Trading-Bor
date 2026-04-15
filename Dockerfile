FROM python:3.11-slim

# System-Abhängigkeiten für TA-Lib
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    wget \
    make \
    && rm -rf /var/lib/apt/lists/*

# TA-Lib C-Bibliothek installieren
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make -j4 \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Logs-Verzeichnis anlegen
RUN mkdir -p logs

EXPOSE 8050

CMD ["python", "main.py", "--mode", "backtest"]
