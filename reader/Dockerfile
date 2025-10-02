FROM python:3.11-slim

WORKDIR /app
COPY reader/ /app
COPY common/ /app/common
RUN pip install --no-cache-dir -r /app/requirements.txt

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
