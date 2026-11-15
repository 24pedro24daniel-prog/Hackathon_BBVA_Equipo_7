# El contexto de build es la RAÍZ del repo (docker-compose: context "..", Render: dockerContext "."), porque la imagen
# lleva los artefactos de ML de modelo/artifacts/ además del código de backend/. Local y Render construyen lo mismo.
FROM python:3.12.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/huggingface \
    ML_ARTIFACTS_DIR=/app/ml/artifacts

WORKDIR /app

# libgomp1: LightGBM (OpenMP) no carga sin ella (OSError libgomp.so.1) en la imagen slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios; /models es el volumen de caché de Whisper (se crea con su dueño para el volumen nombrado)
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home-dir /home/app --create-home app \
    && mkdir -p /models/whisper /models/huggingface \
    && chown -R app:app /models /app

# Directas en requirements.txt y transitivas congeladas en constraints.txt: local y Render instalan exactamente lo mismo.
# pip check corta el build si alguna versión fijada no es compatible con lo que declara otra.
COPY backend/requirements.txt backend/constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt \
    && pip check

# Artefactos de ML (solo lo que usa el backend; motor_recomendaciones no se integra). Cambian poco: van antes del código.
COPY --chown=app:app modelo/artifacts/prediccion_ingreso_egreso /app/ml/artifacts/prediccion_ingreso_egreso
COPY --chown=app:app modelo/artifacts/credit_scoring /app/ml/artifacts/credit_scoring

# Las credenciales (.env) nunca se copian: el .dockerignore de la raíz las excluye y entran por env_file de compose
COPY --chown=app:app backend/ .

USER app
EXPOSE 8000

# --no-proxy-headers: uvicorn no reescribe la IP del cliente con X-Forwarded-For (en Render el cliente puede inyectar
# entradas a la izquierda y por defecto uvicorn confía en 127.0.0.1). La IP real para los límites del login la resuelve
# la app con IP_CLIENTE_CABECERA (Render: CF-Connecting-IP; ver app/core/limites.py y render.yaml).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
