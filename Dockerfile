FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic only needs a placeholder key; the real one comes from the environment at runtime.
RUN SECRET_KEY=build-only DEBUG=False python manage.py collectstatic --noinput \
    && mkdir -p /app/media /app/private_media \
    && chown -R app:app /app/media /app/private_media

USER app

EXPOSE 8000

CMD ["gunicorn", "codehub_ph.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
