FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system smarthire && adduser --system --ingroup smarthire smarthire
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir .
RUN mkdir -p /data/resumes && chown -R smarthire:smarthire /app /data
USER smarthire
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","2"]

