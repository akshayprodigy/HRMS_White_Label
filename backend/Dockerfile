FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmariadb-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Recommended production command: run migrations then start gunicorn
# Note: In a real distributed environment, migrations are usually run separately (e.g., as a CI step)
# to avoid concurrent migration attempts from multiple workers.
CMD ["sh", "-c", "python -m alembic upgrade head && gunicorn -c gunicorn_conf.py app.main:create_app"]
