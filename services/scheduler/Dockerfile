FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY services/scheduler/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY libs /app/libs
COPY services/scheduler /app/services/scheduler

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN chmod +x /app/services/scheduler/entrypoint.sh

CMD ["bash", "-lc", "./services/scheduler/entrypoint.sh"]
