"""Login de las demos (contract.md §12): POST /auth/login, GET /auth/sesion, tokens, límite de intentos, CORS y que
ninguna contraseña quede en el repo."""

import base64
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core import claves_demo, limites, tokens
from app.core.config import BACKEND_DIR, settings
from app.main import CORS_HEADERS, crear_app
from tests._e_util import P, SECRETO_PRUEBA, USUARIOS_PRUEBA, auth_demo, bearer, cliente, cliente_sin_bd, token_de  # noqa: F401
from tests.conftest import API_KEY_PRUEBAS

pytestmark = pytest.mark.usefixtures("auth_demo")

LOGIN = f"{P}/auth/login"
SESION = f"{P}/auth/sesion"
ORIGENES_PRODUCCION = ["http://localhost:5173", "https://cclara.site", "https://www.cclara.site"]


def _error(r, status: int, codigo: str) -> dict:
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert set(err) == {"codigo", "mensaje", "detalles", "request_id"} and err["codigo"] == codigo
    return err


def _partes(token: str) -> tuple[dict, dict, str]:
    def dec(s):
        return json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))

    h, c, f = token.split(".")
    return dec(h), dec(c), f


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).rstrip(b"=").decode()


# ── POST /auth/login ──


@pytest.mark.db
def test_login_ok_devuelve_token_y_empresa(cliente):
    r = cliente.post(LOGIN, json={"usuario": "demo1", "contrasena": "demo1"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"token", "tipo", "expira_en", "expira", "usuario", "empresa_id", "negocio"}
    assert (d["tipo"], d["expira_en"], d["usuario"], d["empresa_id"]) == ("Bearer", 28800, "demo1", "EMP-0001")
    assert d["negocio"] == {"nombre": "Bodega Don Pedro"}
    assert datetime.fromisoformat(d["expira"]).utcoffset().total_seconds() == -5 * 3600
    assert r.headers["cache-control"] == "no-store"
    cabecera, claims, _ = _partes(d["token"])
    assert cabecera == {"alg": "HS256", "typ": "JWT"}
    assert set(claims) == {"sub", "emp", "iat", "exp", "jti"} and claims["exp"] - claims["iat"] == 28800
    assert (claims["sub"], claims["emp"]) == ("demo1", "EMP-0001")
    # El token abre la sesión y sirve para su empresa
    s = cliente.get(SESION, headers={"Authorization": f"Bearer {d['token']}"})
    assert s.status_code == 200 and s.json()["empresa_id"] == "EMP-0001"
    assert cliente.get(f"{P}/empresas/EMP-0001/resumen", headers={"Authorization": f"Bearer {d['token']}"}).status_code == 200


@pytest.mark.db
def test_login_no_distingue_mayusculas_del_usuario(cliente):
    r = cliente.post(LOGIN, json={"usuario": " Demo2 ", "contrasena": "demo2"})
    assert r.status_code == 200 and r.json()["usuario"] == "demo2" and r.json()["empresa_id"] == "EMP-0002"


def test_contrasena_mala_y_usuario_inexistente_dan_el_mismo_error(cliente_sin_bd, monkeypatch):
    llamadas = []
    original = claves_demo.verificar

    def espia(contrasena, hash_):
        llamadas.append(hash_)
        return original(contrasena, hash_)

    monkeypatch.setattr(claves_demo, "verificar", espia)
    mala = cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "otra"})
    nadie = cliente_sin_bd.post(LOGIN, json={"usuario": "nadie", "contrasena": "demo1"})
    e1, e2 = _error(mala, 401, "CREDENCIALES_INVALIDAS"), _error(nadie, 401, "CREDENCIALES_INVALIDAS")
    assert e1["mensaje"] == e2["mensaje"] == "Usuario o contraseña incorrectos."
    assert e1["detalles"] == e2["detalles"] == []
    # Sin enumeración por tiempo: el usuario inexistente también paga un scrypt con los mismos parámetros
    assert len(llamadas) == 2 and all(claves_demo.hash_valido(h) for h in llamadas)
    assert llamadas[0].split(".")[:4] == llamadas[1].split(".")[:4]


@pytest.mark.parametrize("cuerpo", [
    {}, {"usuario": "demo1"}, {"contrasena": "demo1"}, {"usuario": "", "contrasena": "x"},
    {"usuario": "x" * 65, "contrasena": "x"}, {"usuario": "demo1", "contrasena": "x" * 129},
    {"usuario": 1, "contrasena": "demo1"}, {"usuario": "demo1", "contrasena": ["demo1"]}, ["demo1", "demo1"],
])  # fmt: skip
def test_login_valida_el_body_con_422(cliente_sin_bd, cuerpo):
    err = _error(cliente_sin_bd.post(LOGIN, json=cuerpo), 422, "VALIDACION")
    assert err["detalles"] and {"campo", "problema"} <= set(err["detalles"][0])


def test_login_json_invalido_422(cliente_sin_bd):
    r = cliente_sin_bd.post(LOGIN, content=b"{no es json", headers={"Content-Type": "application/json"})
    _error(r, 422, "VALIDACION")


def test_login_sin_configurar_503(cliente_sin_bd, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SECRET", SecretStr(""))
    _error(cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "demo1"}), 503, "SERVICIO_NO_DISPONIBLE")


@pytest.mark.db
def test_login_de_empresa_que_no_esta_en_la_bd_503(cliente):
    _error(cliente.post(LOGIN, json={"usuario": "demo3", "contrasena": "demo3"}), 503, "SERVICIO_NO_DISPONIBLE")


@pytest.mark.db
def test_limite_de_intentos_por_ip_con_retry_after(cliente, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FALLOS", 3)
    monkeypatch.setattr(settings, "AUTH_LOGIN_VENTANA_S", 600)
    reloj = [1000.0]
    monkeypatch.setattr(limites, "_reloj", lambda: reloj[0])
    for i in range(3):
        reloj[0] += 10
        _error(cliente.post(LOGIN, json={"usuario": "demo1", "contrasena": f"mala{i}"}), 401, "CREDENCIALES_INVALIDAS")
    # Bloqueado aunque ahora la contraseña sea la correcta; Retry-After = hasta que salga de la ventana el 1.er fallo
    r = cliente.post(LOGIN, json={"usuario": "demo1", "contrasena": "demo1"})
    err = _error(r, 429, "DEMASIADOS_INTENTOS")
    assert r.headers["retry-after"] == "580" and "min" in err["mensaje"]
    reloj[0] += 580
    assert cliente.post(LOGIN, json={"usuario": "demo1", "contrasena": "demo1"}).status_code == 200


def test_la_ip_no_se_falsifica_con_cabeceras_en_local(cliente_sin_bd, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FALLOS", 2)
    for ip in ("1.1.1.1", "2.2.2.2"):
        cabeceras = {"X-Forwarded-For": ip, "CF-Connecting-IP": ip, "X-Real-IP": ip}
        cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers=cabeceras)
    r = cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers={"X-Forwarded-For": "3.3.3.3"})
    _error(r, 429, "DEMASIADOS_INTENTOS")


def test_con_cabecera_de_proxy_configurada_cada_ip_cuenta_aparte(cliente_sin_bd, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FALLOS", 2)
    monkeypatch.setattr(settings, "IP_CLIENTE_CABECERA", "CF-Connecting-IP")
    a = {"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": "9.9.9.9, 203.0.113.7"}
    for _ in range(2):
        cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers=a)
    _error(cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers=a), 429, "DEMASIADOS_INTENTOS")
    # Otra IP real (cambiar X-Forwarded-For no sirve de nada)
    b = {"CF-Connecting-IP": "198.51.100.20"}
    _error(cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers=b), 401, "CREDENCIALES_INVALIDAS")
    # Una cabecera que no es una IP cae a la IP de la conexión (no abre un balde nuevo por cada valor inventado)
    for basura in ("no-es-ip", "1.2.3.4.5"):
        cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers={"CF-Connecting-IP": basura})
    r = cliente_sin_bd.post(LOGIN, json={"usuario": "demo1", "contrasena": "mala"}, headers={"CF-Connecting-IP": "x"})
    _error(r, 429, "DEMASIADOS_INTENTOS")


# ── tokens ──


def test_token_vencido_sesion_expirada(cliente_sin_bd, monkeypatch):
    cabecera = bearer("demo1")
    _, claims, _ = _partes(cabecera["Authorization"].split()[1])
    monkeypatch.setattr(tokens, "_ahora", lambda: claims["exp"])
    r = cliente_sin_bd.get(SESION, headers=cabecera)
    _error(r, 401, "SESION_EXPIRADA")
    _error(cliente_sin_bd.get(f"{P}/empresas/EMP-0001/resumen", headers=cabecera), 401, "SESION_EXPIRADA")


def test_token_manipulado_no_autorizado(cliente_sin_bd):
    token = token_de("demo1")
    cabecera, claims, firma = _partes(token)
    h = token.split(".")[0]
    otra_empresa = f"{h}.{_b64({**claims, 'emp': 'EMP-0002'})}.{firma}"
    mas_tiempo = f"{h}.{_b64({**claims, 'exp': claims['exp'] + 99999})}.{firma}"
    sin_alg = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{token.split('.')[1]}."
    otro_alg = f"{_b64({'alg': 'HS512', 'typ': 'JWT'})}.{token.split('.')[1]}.{firma}"
    firma_cambiada = f"{token[:-2]}{'AA' if token[-2:] != 'AA' else 'BB'}"
    for malo in (otra_empresa, mas_tiempo, sin_alg, otro_alg, firma_cambiada, "basura", token + ".x", "a.b.c", ""):
        r = cliente_sin_bd.get(SESION, headers={"Authorization": f"Bearer {malo}"})
        _error(r, 401, "NO_AUTORIZADO")
    _error(cliente_sin_bd.get(SESION, headers={"Authorization": f"Basic {token}"}), 401, "NO_AUTORIZADO")


def test_token_firmado_con_otro_secreto(cliente_sin_bd):
    falso, _ = tokens.emitir("otro-secreto-que-no-es-el-del-servidor-1234567890", "demo1", "EMP-0001", 28800)
    _error(cliente_sin_bd.get(SESION, headers={"Authorization": f"Bearer {falso}"}), 401, "NO_AUTORIZADO")
    _error(cliente_sin_bd.get(f"{P}/empresas/EMP-0001/resumen", headers={"Authorization": f"Bearer {falso}"}),
           401, "NO_AUTORIZADO")  # fmt: skip


def test_token_con_ttl_mayor_al_configurado_no_sirve(cliente_sin_bd):
    largo, _ = tokens.emitir(SECRETO_PRUEBA, "demo1", "EMP-0001", 28800 * 10)
    _error(cliente_sin_bd.get(SESION, headers={"Authorization": f"Bearer {largo}"}), 401, "NO_AUTORIZADO")


def test_cambiar_la_empresa_del_usuario_invalida_sus_tokens(cliente_sin_bd, monkeypatch):
    cabecera = bearer("demo2")
    monkeypatch.setattr(settings, "AUTH_USUARIOS", "USR-01:EMP-0001,USR-02:EMP-0005,USR-03:EMP-0999")
    _error(cliente_sin_bd.get(SESION, headers=cabecera), 401, "NO_AUTORIZADO")


def test_servidor_sin_secreto_rechaza_todo_bearer(cliente_sin_bd, monkeypatch):
    cabecera = bearer("demo1")
    monkeypatch.setattr(settings, "AUTH_SECRET", SecretStr("corto"))
    _error(cliente_sin_bd.get(SESION, headers=cabecera), 401, "NO_AUTORIZADO")


# ── GET /auth/sesion ──


@pytest.mark.db
def test_sesion_devuelve_usuario_empresa_y_negocio(cliente):
    d = cliente.get(SESION, headers=bearer("demo2")).json()
    assert set(d) == {"usuario", "empresa_id", "expira", "negocio"}
    assert (d["usuario"], d["empresa_id"], d["negocio"]["nombre"]) == ("demo2", "EMP-0002", "Pedro · día 3")


def test_sesion_sin_credenciales_o_con_api_key_401(cliente_sin_bd):
    _error(cliente_sin_bd.get(SESION), 401, "NO_AUTORIZADO")
    _error(cliente_sin_bd.get(SESION, headers={"X-API-Key": API_KEY_PRUEBAS}), 401, "NO_AUTORIZADO")


# ── X-API-Key y rutas públicas ──


@pytest.mark.db
def test_x_api_key_sigue_funcionando_para_cualquier_empresa(cliente):
    for emp in ("EMP-0001", "EMP-0002"):
        assert cliente.get(f"{P}/empresas/{emp}/resumen", headers={"X-API-Key": API_KEY_PRUEBAS}).status_code == 200
    # Una API key inválida es 401 aunque venga también un Bearer válido
    r = cliente.get(f"{P}/empresas/EMP-0001/resumen", headers={"X-API-Key": "otra", **bearer("demo1")})
    _error(r, 401, "NO_AUTORIZADO")


def test_health_es_publico(cliente_sin_bd):
    assert cliente_sin_bd.get(f"{P}/health").status_code == 200


def test_rutas_protegidas_sin_credenciales_piden_bearer(cliente_sin_bd):
    r = cliente_sin_bd.get(f"{P}/empresas/EMP-0001/resumen")
    err = _error(r, 401, "NO_AUTORIZADO")
    assert "Bearer" in err["mensaje"] and r.headers["www-authenticate"] == "Bearer"


# ── CORS ──


def test_preflight_cors_desde_cclara_site():
    from fastapi.testclient import TestClient

    render = BACKEND_DIR.parent / "render.yaml"
    if render.exists():  # fuera de docker: el blueprint de Render declara exactamente estos orígenes
        assert f"value: {','.join(ORIGENES_PRODUCCION)}" in render.read_text(encoding="utf-8")
    c = TestClient(crear_app(ORIGENES_PRODUCCION))
    pedido = {"Access-Control-Request-Method": "POST",
              "Access-Control-Request-Headers": "authorization,content-type,idempotency-key,x-api-key"}  # fmt: skip
    for origen in ("https://cclara.site", "https://www.cclara.site", "http://localhost:5173"):
        r = c.options(LOGIN, headers={"Origin": origen, **pedido})
        assert r.status_code == 200, r.text
        assert r.headers["access-control-allow-origin"] == origen
        assert "access-control-allow-credentials" not in r.headers
        permitidos = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
        assert {h.lower() for h in CORS_HEADERS} <= permitidos
    r = c.options(LOGIN, headers={"Origin": "https://cclara.site.evil.com", **pedido})
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    # Un header que no está en la lista no pasa el preflight
    r = c.options(LOGIN, headers={"Origin": "https://cclara.site", "Access-Control-Request-Method": "POST",
                                  "Access-Control-Request-Headers": "x-otra-cosa"})  # fmt: skip
    assert r.status_code == 400


def test_respuesta_cors_expone_retry_after_y_request_id():
    from fastapi.testclient import TestClient

    c = TestClient(crear_app(ORIGENES_PRODUCCION))
    r = c.get(f"{P}/auth/sesion", headers={"Origin": "https://cclara.site"})
    assert r.status_code == 401 and r.headers["access-control-allow-origin"] == "https://cclara.site"
    expuestos = {h.strip().lower() for h in r.headers["access-control-expose-headers"].split(",")}
    assert {"retry-after", "x-request-id"} <= expuestos


# ── contraseñas fuera del repo ──


def test_hash_scrypt_ida_y_vuelta():
    h = claves_demo.generar_hash("una-clave")
    assert claves_demo.hash_valido(h) and h.startswith("scrypt.16384.8.1.")
    assert claves_demo.verificar("una-clave", h) and not claves_demo.verificar("una-clave ", h)
    assert claves_demo.generar_hash("una-clave") != h  # sal aleatoria
    assert not claves_demo.verificar("x", "scrypt.1048576.8.1.AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert not claves_demo.verificar("x", "texto-plano")


def test_cli_imprime_la_entrada_completa(capsys):
    assert claves_demo.main(["--usuario", "USR-09", "--login", "Alguien", "clave"]) == 0
    usuario, login, hash_ = capsys.readouterr().out.strip().split(":")
    assert (usuario, login) == ("USR-09", "alguien") and claves_demo.verificar("clave", hash_)


def test_ninguna_contrasena_en_claro_en_el_codigo_ni_en_parametros():
    archivos = [p for p in (BACKEND_DIR / "app").rglob("*") if p.is_file() and p.suffix != ".pyc"]
    archivos += [BACKEND_DIR / "parametros.env", BACKEND_DIR / "example.env"]
    prohibidos = {clave for _, clave, _, _ in USUARIOS_PRUEBA} | {login for login, _, _, _ in USUARIOS_PRUEBA}
    hash_completo = re.compile(r"scrypt\.\d+\.\d+\.\d+\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{32,}")
    for ruta in archivos:
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        for p in prohibidos:
            assert not re.search(rf"\b{re.escape(p)}\b", texto, re.IGNORECASE), f"'{p}' aparece en {ruta}"
        assert not hash_completo.search(texto), f"hay un hash de contraseña en {ruta}"
        assert not re.search(r"^AUTH_(SECRET|CREDENCIALES)=\S", texto, re.MULTILINE), f"credencial con valor en {ruta}"


def test_credenciales_de_auth_no_se_ven_en_repr():
    s = type(settings)(_env_file=None, AUTH_SECRET="s" * 40, AUTH_CREDENCIALES="USR-01:x:scrypt.secreto")
    assert "s" * 40 not in repr(s) and "scrypt.secreto" not in str(s.model_dump())


def test_ruta_de_este_archivo_no_se_escanea():
    # Los logins de prueba viven en tests/ (que no va al código de la app): el escaneo de arriba no los cuenta.
    assert Path(__file__).resolve().parent.name == "tests"
