FROM python:3.11-slim

WORKDIR /app

# Bagimliliklari once kur (layer cache icin)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarini kopyala (.env haric -- Railway Variables kullanilir)
COPY . .

# Log dizini olustur
RUN mkdir -p logs

CMD ["python", "paper_trader.py"]
