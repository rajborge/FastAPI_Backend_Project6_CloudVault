FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Tesseract provides OCR for uploaded image files.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-semantic.txt ./
ARG ENABLE_SEMANTIC_SEARCH=false
RUN if [ "$ENABLE_SEMANTIC_SEARCH" = "true" ]; then \
        pip install --no-cache-dir -r requirements-semantic.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi

COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY app ./app

RUN mkdir -p /app/uploads /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
