FROM python:3.12-slim AS runtime

# Install system dependencies for OCR and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    # Running `python scripts/foo.py` puts /app/scripts on sys.path, not /app,
    # so the `app` package is not importable. Uvicorn and Alembic each add the
    # working directory themselves; plain scripts do not.
    PYTHONPATH=/app

WORKDIR /app

# Create non-root user
RUN addgroup --system smarthire && adduser --system --ingroup smarthire smarthire

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./

# Set ownership
RUN chown -R smarthire:smarthire /app

USER smarthire

EXPOSE 8000

# Railway injects PORT at runtime; 8000 is the local fallback.
# wait_for_db.py guards against Railway's private-network DNS being unresolvable
# for the first seconds of container life, which would otherwise crash-loop the
# deploy before migrations could run.
CMD sh -c "python scripts/wait_for_db.py && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"


