FROM python:3.11-slim

WORKDIR /app

COPY services/migrate/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY libs /app/libs
COPY migrations /app/migrations
COPY scripts /app/scripts

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "scripts/apply_migrations.py"]
