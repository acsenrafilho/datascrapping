from __future__ import annotations

import logging
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

IBGE_UF_URL = "https://brasilapi.com.br/api/ibge/uf/v1/{state}"
IBGE_CITIES_URL = (
    "https://brasilapi.com.br/api/ibge/municipios/v1/{state}"
    "?providers=dados-abertos-br,gov,wikipedia"
)
DEFAULT_TIMEOUT = 15


class GeoValidationError(ValueError):
    """City/UF failed IBGE validation."""


def normalize_city_state(city: str, state: str) -> tuple[str, str]:
    return city.strip().upper(), state.strip().upper()


def city_in_municipios(city_upper: str, municipios: list[dict[str, Any]]) -> bool:
    names = {str(item.get("nome") or "").upper() for item in municipios}
    return city_upper in names


def validate_city_state(
    city: str,
    state: str,
    *,
    http_get: Callable[..., Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str]:
    """Validate city/UF via BrasilAPI IBGE endpoints.

    Returns normalized (city, state) on success.
    Raises GeoValidationError on failure.
    """
    city_u, state_u = normalize_city_state(city, state)
    if len(state_u) != 2:
        raise GeoValidationError(f"UF inválida: {state!r} (use 2 letras, ex.: SP)")

    getter = http_get or requests.get

    try:
        uf_resp = getter(IBGE_UF_URL.format(state=state_u), timeout=timeout)
        uf_resp.raise_for_status()
        uf_data = uf_resp.json()
    except Exception as exc:
        raise GeoValidationError(
            f"Não foi possível validar a UF {state_u} na BrasilAPI: {exc}"
        ) from exc

    if not isinstance(uf_data, dict) or not uf_data.get("sigla"):
        raise GeoValidationError(f"UF não encontrada na BrasilAPI: {state_u}")

    try:
        cities_resp = getter(IBGE_CITIES_URL.format(state=state_u), timeout=timeout)
        cities_resp.raise_for_status()
        cities_data = cities_resp.json()
    except Exception as exc:
        raise GeoValidationError(
            f"Não foi possível listar municípios de {state_u}: {exc}"
        ) from exc

    if not isinstance(cities_data, list):
        raise GeoValidationError(
            f"Resposta inesperada de municípios para {state_u}"
        )

    if not city_in_municipios(city_u, cities_data):
        raise GeoValidationError(
            f"Cidade {city!r} não encontrada no IBGE para UF {state_u}"
        )

    logger.info("Geo check OK: %s / %s", city_u, state_u)
    return city_u, state_u
