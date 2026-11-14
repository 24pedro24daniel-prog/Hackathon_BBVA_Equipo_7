FROM python:3.12.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/huggingface

WORKDIR /app

# Usuario sin privilegios; /models es el volumen de caché de Whisper (se crea con su dueño para el volumen nombrado)
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home-dir /home/app --create-home app \
    && mkdir -p /models/whisper /models/huggingface \
    && chown -R app:app /models /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Las credenciales (.env) nunca se copian: .dockerignore las excluye y entran por env_file de compose
COPY --chown=app:app . .

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
