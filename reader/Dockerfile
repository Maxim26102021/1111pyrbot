FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for TgCrypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY reader/ /app
COPY common/ /app/common
RUN pip install --no-cache-dir -r /app/requirements.txt

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
