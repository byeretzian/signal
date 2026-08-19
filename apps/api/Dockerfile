FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY src ./src
COPY database ./database
RUN pip install --no-cache-dir .
EXPOSE 8000
