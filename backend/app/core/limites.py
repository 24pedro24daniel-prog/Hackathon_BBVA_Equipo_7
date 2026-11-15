"""Límites en memoria (una sola instancia del backend, como en Render free) e IP real del cliente.

- `LIMITE_LOGIN`: fallos de login por IP (ventana deslizante).
- `LIMITE_IA`: usos de las rutas que gastan LLM/VLM/Whisper/R2 por sesión (`jti`) y por usuario (todas sus sesiones).

Los contadores se pierden al reiniciar el proceso (aceptado para la demo). La memoria está acotada: se podan las
entradas vencidas y, si aun así hay demasiadas claves, se descartan las más antiguas.
"""

import ipaddress
import math
import threading
import time
from collections import deque

from fastapi import Request

from app.core.config import settings

MAX_CLAVES = 20_000


def _reloj() -> float:
    """Reloj monótono (los tests lo reemplazan)."""
    return time.monotonic()


class LimiteVentana:
    """Ventana deslizante por clave: como mucho `maximo` eventos en los últimos `ventana_s` segundos."""

    def __init__(self) -> None:
        self._eventos: dict[str, deque[float]] = {}
        self._candado = threading.Lock()

    def _vigentes(self, clave: str, ventana_s: float, ahora: float) -> deque[float]:
        cola = self._eventos.get(clave)
        if cola is None:
            return deque()
        while cola and cola[0] <= ahora - ventana_s:
            cola.popleft()
        if not cola:
            del self._eventos[clave]
        return cola

    def _podar(self, ventana_s: float, ahora: float) -> None:
        if len(self._eventos) < MAX_CLAVES:
            return
        for clave in list(self._eventos):
            self._vigentes(clave, ventana_s, ahora)
        while len(self._eventos) >= MAX_CLAVES:
            del self._eventos[next(iter(self._eventos))]

    @staticmethod
    def _espera(cola: deque[float], maximo: int, ventana_s: float, ahora: float) -> int:
        if len(cola) < maximo:
            return 0
        # Se libera un cupo cuando sale de la ventana el evento que deja `maximo - 1` dentro.
        return max(1, math.ceil(cola[len(cola) - maximo] + ventana_s - ahora))

    def espera(self, clave: str, maximo: int, ventana_s: float) -> int:
        """Segundos hasta que haya cupo (0 = hay cupo). No registra nada."""
        with self._candado:
            ahora = _reloj()
            return self._espera(self._vigentes(clave, ventana_s, ahora), maximo, ventana_s, ahora)

    def registrar(self, clave: str, ventana_s: float) -> None:
        with self._candado:
            ahora = _reloj()
            self._podar(ventana_s, ahora)
            self._eventos.setdefault(clave, deque()).append(ahora)

    def consumir(self, limites: list[tuple[str, int]], ventana_s: float) -> int:
        """Todo o nada: si alguna clave no tiene cupo devuelve los segundos de espera (sin registrar); si no, registra un
        evento en cada clave y devuelve 0."""
        with self._candado:
            ahora = _reloj()
            espera = max((self._espera(self._vigentes(c, ventana_s, ahora), m, ventana_s, ahora) for c, m in limites),
                         default=0)  # fmt: skip
            if espera:
                return espera
            self._podar(ventana_s, ahora)
            for clave, _ in limites:
                self._eventos.setdefault(clave, deque()).append(ahora)
            return 0

    def reiniciar(self) -> None:
        with self._candado:
            self._eventos.clear()


LIMITE_LOGIN = LimiteVentana()
LIMITE_IA = LimiteVentana()


def _ip_valida(texto: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((texto or "").strip()))
    except ValueError:
        return None


def ip_cliente(request: Request) -> str:
    """IP del cliente para los límites.

    Con IP_CLIENTE_CABECERA (Render: `CF-Connecting-IP`, que pone y sobreescribe Cloudflare delante de Render) se usa esa
    cabecera; si falta o no es una IP, la de la conexión TCP. Sin ella (local) solo la conexión TCP: `X-Forwarded-For`
    nunca se lee (en Render el cliente puede inyectar entradas a la izquierda) y uvicorn corre con --no-proxy-headers.
    """
    cabecera = settings.IP_CLIENTE_CABECERA.strip()
    if cabecera and (ip := _ip_valida(request.headers.get(cabecera))):
        return ip
    return request.client.host if request.client else "desconocida"
