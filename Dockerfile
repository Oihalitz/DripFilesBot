FROM python:3.14-slim

WORKDIR /app

# gcc para compilar TgCrypto
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/app/downloads"]

CMD ["python", "main.py"]
