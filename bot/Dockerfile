FROM python:3.11-slim

WORKDIR /app
COPY bot/ /app
COPY common/ /app/common

# Установка curl и build dependencies для TgCrypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/requirements.txt

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
