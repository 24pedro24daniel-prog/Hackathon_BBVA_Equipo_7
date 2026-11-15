"""Fixtures comunes.

- BD: usa SIEMPRE la BD de pruebas (POSTGRES_TEST_DB). Se recrea y siembra una vez por sesión; cada test corre
  dentro de una transacción que se revierte al final. Si Postgres no está accesible, los tests que piden `db`
  se saltan con un mensaje claro (los demás corren igual).
- IA: el LLM (OpenRouter) y Whisper nunca se llaman de verdad. `llm_falso` y `whisper_falso` simulan respuestas.
"""

import io
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.reset import resetear
from app.db.session import crear_engine, get_db
from app.main import app
from app.services.ingesta import almacenamiento, llm_client, transcriptor

API_KEY_PRUEBAS = "clave-de-pruebas-cajaclara"


# ── IA: nunca real ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _sin_ia_real(monkeypatch):
    def _post_prohibido(*_a, **_k):
        raise AssertionError("Un test intentó llamar al LLM real (usa la fixture llm_falso)")

    def _whisper_prohibido():
        raise AssertionError("Un test intentó cargar Whisper real (usa la fixture whisper_falso)")

    monkeypatch.setattr(llm_client, "_post", _post_prohibido)
    monkeypatch.setattr(transcriptor, "_cargar_modelo", _whisper_prohibido)
    monkeypatch.setattr(transcriptor, "_modelo", None)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr(""))
    monkeypatch.setattr(settings, "API_KEY", SecretStr(API_KEY_PRUEBAS))


@pytest.fixture(autouse=True)
def _forecast_baseline_por_defecto(monkeypatch):
    """Los tests de cifras de la demo (30/11 = −650, etc.) usan el baseline determinístico. Los tests del LightGBM piden
    el motor explícitamente (fixture `motor_lightgbm`) y se saltan si no están los artefactos."""
    monkeypatch.setattr(settings, "FORECAST_MOTOR", "baseline")


@pytest.fixture
def motor_lightgbm(monkeypatch):
    """FORECAST_MOTOR=lightgbm con los artefactos reales (salta el test si no están o no cargan)."""
    from app.services.finanzas import modelo_ml

    monkeypatch.setattr(settings, "FORECAST_MOTOR", "lightgbm")
    modelo_ml._FORECAST.limpiar()
    modelo, motivo = modelo_ml.cargar_forecast()
    if modelo is None:
        pytest.skip(f"Modelo LightGBM no disponible en {settings.ml_artifacts_dir}: {motivo}")
    yield modelo
    modelo_ml._FORECAST.limpiar()


@pytest.fixture(autouse=True)
def _sin_r2_real(monkeypatch):
    """Nunca se crea un cliente boto3 real ni se usan credenciales R2 del .env en los tests."""

    def _cliente_prohibido(*_a, **_k):
        raise AssertionError("Un test intentó crear un cliente boto3 real (usa la fixture s3_falso)")

    import boto3
    import boto3.session

    monkeypatch.setattr(boto3, "client", _cliente_prohibido)
    monkeypatch.setattr(boto3.session.Session, "client", _cliente_prohibido)
    monkeypatch.setattr(almacenamiento, "_crear_cliente", _cliente_prohibido)
    monkeypatch.setattr(almacenamiento, "_cliente", None)
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", SecretStr(""))
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", SecretStr(""))


@pytest.fixture
def llm_falso(monkeypatch):
    """Reemplaza la llamada HTTP a OpenRouter. Configura `.respuesta` (dict) o `.error` (excepción)."""
    estado = SimpleNamespace(llamadas=[], error=None,
                             respuesta={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})  # fmt: skip

    def _post(url, payload, headers, timeout):
        estado.llamadas.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        if estado.error is not None:
            raise estado.error
        return estado.respuesta

    monkeypatch.setattr(llm_client, "_post", _post)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr("sk-or-prueba"))
    return estado


@pytest.fixture
def whisper_falso(monkeypatch):
    """Modelo de Whisper falso: `.texto` es lo que "se escucha"."""
    estado = SimpleNamespace(texto="vendí dos cervezas", cargas=0, archivos=[])

    class _Modelo:
        def transcribe(self, ruta, **_kw):
            estado.archivos.append(ruta)
            return [SimpleNamespace(text=f" {estado.texto} ")], SimpleNamespace(language="es")

    def _cargar():
        estado.cargas += 1
        return _Modelo()

    monkeypatch.setattr(transcriptor, "_cargar_modelo", _cargar)
    return estado


class ClienteS3Falso:
    """Cliente S3 en memoria: `objetos[clave] = {"cuerpo": bytes, "content_type": str}`."""

    def __init__(self):
        self.objetos: dict[str, dict] = {}
        self.presignados: list[dict] = []
        self.llamadas: list[tuple[str, str]] = []

    def generate_presigned_url(self, operacion, Params, ExpiresIn, HttpMethod=None):  # noqa: N803 - firma de boto3
        self.presignados.append({"operacion": operacion, "params": Params, "expires_in": ExpiresIn,
                                 "metodo": HttpMethod})  # fmt: skip
        return f"https://falso.r2.test/{Params['Bucket']}/{Params['Key']}?X-Amz-Expires={ExpiresIn}&X-Amz-Signature=abc"

    def _obtener(self, clave: str) -> dict:
        from botocore.exceptions import ClientError

        if clave not in self.objetos:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return self.objetos[clave]

    def head_object(self, Bucket, Key):  # noqa: N803
        self.llamadas.append(("head", Key))
        o = self._obtener(Key)
        return {"ContentLength": o["tamano"] if o.get("tamano") is not None else len(o["cuerpo"]), "ContentType": o["content_type"]}

    def get_object(self, Bucket, Key):  # noqa: N803
        self.llamadas.append(("get", Key))
        return {"Body": io.BytesIO(self._obtener(Key)["cuerpo"])}

    def poner(self, clave: str, cuerpo: bytes = b"datos", content_type: str = "audio/ogg", tamano: int | None = None):
        self.objetos[clave] = {"cuerpo": cuerpo, "content_type": content_type, "tamano": tamano}
        return f"r2://{clave}"


@pytest.fixture
def s3_falso(monkeypatch) -> ClienteS3Falso:
    """R2 configurado con un cliente S3 en memoria (sin red)."""
    falso = ClienteS3Falso()
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "cuenta-de-prueba")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", SecretStr("ak-prueba"))
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", SecretStr("sk-prueba"))
    monkeypatch.setattr(almacenamiento, "_cliente", falso)
    return falso


# ── BD de pruebas ───────────────────────────────────────────────────────────────────────────────


def _url_pruebas() -> str:
    url = settings.test_database_url
    if make_url(url).database == settings.POSTGRES_DB:
        raise RuntimeError("La BD de pruebas no puede ser la BD principal")
    return url


@pytest.fixture(scope="session")
def engine_pruebas() -> Iterator[Engine]:
    url = _url_pruebas()
    engine = crear_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        destino = make_url(url).render_as_string(hide_password=True)
        pytest.skip(f"Postgres no accesible en {destino} ({type(exc).__name__}). "
                    "Levanta la BD con `docker compose up -d db` para correr los tests de BD.")  # fmt: skip
    resetear(engine, con_seed=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine_pruebas: Engine) -> Iterator[Session]:
    """Sesión dentro de una transacción que se revierte: cada test ve el seed intacto."""
    conexion = engine_pruebas.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint", autoflush=False,
                     expire_on_commit=False)  # fmt: skip
    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()


# ── Cliente HTTP ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _sesiones_sin_conexion():
    """Fábrica de sesiones a la BD de pruebas que no conecta hasta usarse (los stubs no tocan la BD)."""
    engine = crear_engine(_url_pruebas(), connect_args={"connect_timeout": 2})
    yield sessionmaker(bind=engine)
    engine.dispose()


def _cliente(fabrica, headers: dict) -> Iterator[TestClient]:
    def _get_db():
        sesion = fabrica()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, headers=headers) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client(_sesiones_sin_conexion) -> Iterator[TestClient]:
    """Cliente con X-API-Key. get_db apunta a la BD de pruebas (no requiere que esté levantada)."""
    yield from _cliente(_sesiones_sin_conexion, {"X-API-Key": API_KEY_PRUEBAS})


@pytest.fixture
def client_sin_key(_sesiones_sin_conexion) -> Iterator[TestClient]:
    yield from _cliente(_sesiones_sin_conexion, {})


@pytest.fixture
def client_db(db: Session) -> Iterator[TestClient]:
    """Cliente cuyo get_db usa la sesión transaccional `db` (los cambios se revierten al final)."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"X-API-Key": API_KEY_PRUEBAS}) as c:
        yield c
    app.dependency_overrides.clear()
