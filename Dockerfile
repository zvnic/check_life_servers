FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system cls && adduser --system --ingroup cls --home /app cls

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[dev]"

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests

USER cls
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

