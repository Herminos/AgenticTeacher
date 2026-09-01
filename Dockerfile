FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY config ./config
COPY ingest.py ./ingest.py
COPY scripts ./scripts
RUN python scripts/check_python.py

ENV PYTHONUNBUFFERED=1 \
    CC=/usr/bin/gcc
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
