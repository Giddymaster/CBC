# Backend image. Multi-stage so the runtime layer carries no build toolchain.
FROM python:3.13-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Pillow and psycopg need headers at build time, not at run time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /install /usr/local
COPY . .

# Static files are hashed and compressed into the image at build time, so the
# container starts fast and immutable. A throwaway key satisfies the DEBUG=false
# startup guard; it is never used to serve anything.
RUN DJANGO_SETTINGS_MODULE=config.settings \
    DEBUG=false \
    SECRET_KEY=build-time-only-not-used-to-serve \
    python manage.py collectstatic --noinput

# Learner photos and generated report cards live here; a volume mounts over it.
RUN mkdir -p /app/media /app/staticfiles

# Run as a non-root user: this process serves a register of minors' records.
RUN useradd --create-home --uid 10001 cbc \
    && chown -R cbc:cbc /app/media
USER cbc

EXPOSE 8000

# Migrations are deliberately NOT run here. An image that migrates on start would
# race itself the moment there is more than one replica; run them as an explicit
# deploy step (see DEPLOY.md).
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-"]
