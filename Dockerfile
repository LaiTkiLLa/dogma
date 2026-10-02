FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY pyproject.toml alembic.ini ARCHITECTURE.md ./
COPY app ./app

RUN pip install --upgrade pip \
    && pip install .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 10000

# Default command for the API service (overridden in compose).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
