"""BrasilAPI CNPJ client for places.cnpj (ported from company_federal_scrapper)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from datascrapping.scrapers.places.extract import format_cnpj
from datascrapping.scrapers.places.models import empty_full_extras

logger = logging.getLogger(__name__)

BRASIL_API_URL = "https://brasilapi.com.br/api/cnpj/v1"
REQUEST_TIMEOUT = 15
RATE_LIMIT_DELAY = 0.1
MAX_RETRIES = 2
USER_AGENT = "AurisBot/1.0 (+https://leadcontrol.ia.br)"


@dataclass
class FederalFetchResult:
    data: dict[str, Any] | None
    status: str
    reason: str


def fetch_cnpj(
    cnpj: str,
    *,
    session: requests.Session | None = None,
    sleep_fn=time.sleep,
) -> FederalFetchResult:
    """GET BrasilAPI /api/cnpj/v1/{cnpj} with retry on 429 and timeouts."""
    url = f"{BRASIL_API_URL}/{cnpj}"
    http = session or requests.Session()
    logger.info("Fetching BrasilAPI CNPJ: %s", cnpj)

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            if attempt > 1:
                wait_time = 2 ** (attempt - 1)
                logger.info(
                    "Retry attempt %s for CNPJ %s — waiting %ss",
                    attempt,
                    cnpj,
                    wait_time,
                )
                sleep_fn(wait_time)
            else:
                sleep_fn(RATE_LIMIT_DELAY)

            response = http.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )

            if response.status_code == 200:
                return FederalFetchResult(
                    data=response.json(),
                    status="completed",
                    reason="Successfully fetched federal data",
                )
            if response.status_code == 404:
                return FederalFetchResult(
                    data=None,
                    status="completed",
                    reason="CNPJ not found in federal registry",
                )
            if response.status_code == 429:
                if attempt <= MAX_RETRIES:
                    logger.warning(
                        "BrasilAPI rate limit (attempt %s), will retry", attempt
                    )
                    continue
                return FederalFetchResult(
                    data=None,
                    status="failed",
                    reason="API rate limit exceeded",
                )

            return FederalFetchResult(
                data=None,
                status="failed",
                reason=f"API error: HTTP {response.status_code}",
            )

        except requests.exceptions.ConnectTimeout:
            if attempt > MAX_RETRIES:
                return FederalFetchResult(
                    data=None,
                    status="failed",
                    reason=f"API connection timeout (after {attempt} attempts)",
                )
            continue
        except requests.exceptions.ReadTimeout:
            if attempt > MAX_RETRIES:
                return FederalFetchResult(
                    data=None,
                    status="failed",
                    reason=f"API read timeout (after {attempt} attempts)",
                )
            continue
        except requests.exceptions.Timeout:
            if attempt > MAX_RETRIES:
                return FederalFetchResult(
                    data=None,
                    status="failed",
                    reason=f"API request timeout (after {attempt} attempts)",
                )
            continue
        except requests.exceptions.RequestException as exc:
            return FederalFetchResult(
                data=None,
                status="failed",
                reason=f"API request failed: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 — mirror backend fail-closed
            return FederalFetchResult(
                data=None,
                status="failed",
                reason=f"Unexpected error: {exc}",
            )

    return FederalFetchResult(
        data=None,
        status="failed",
        reason="API request failed - max retries exceeded",
    )


def _str_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _pad_cep(value: Any) -> str:
    digits = re.sub(r"\D", "", _str_field(value))
    if not digits:
        return ""
    return digits.zfill(8)[-8:]


def build_fiscal_endereco(data: dict[str, Any]) -> str:
    tipo = _str_field(data.get("descricao_tipo_de_logradouro"))
    logradouro = _str_field(data.get("logradouro"))
    numero = _str_field(data.get("numero"))
    complemento = _str_field(data.get("complemento"))
    bairro = _str_field(data.get("bairro"))
    municipio = _str_field(data.get("municipio"))
    uf = _str_field(data.get("uf"))
    cep = _pad_cep(data.get("cep"))

    street = " ".join(p for p in (tipo, logradouro) if p).strip()
    line_parts: list[str] = []
    if street:
        if numero:
            street = f"{street}, {numero}"
        if complemento:
            street = f"{street} {complemento}".strip()
        line_parts.append(street)
    if bairro:
        line_parts.append(bairro)
    city_uf = "/".join(p for p in (municipio, uf) if p)
    if city_uf:
        line_parts.append(city_uf)
    if cep:
        line_parts.append(f"CEP {cep}")
    return " - ".join(line_parts)


def _flatten_cnaes_secundarios(raw: Any) -> str:
    if not isinstance(raw, list):
        return ""
    parts: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = _str_field(item.get("codigo"))
        desc = _str_field(item.get("descricao"))
        if code or desc:
            parts.append(f"{code}:{desc}" if code else desc)
    return "|".join(parts)


def map_federal_to_row(api_json: dict[str, Any] | None) -> dict[str, str]:
    """Project BrasilAPI JSON into FULL_EXTRA_FIELDS (federal columns only)."""
    extras = empty_full_extras()
    if not api_json:
        return extras

    cnpj_digits = re.sub(r"\D", "", _str_field(api_json.get("cnpj")))
    extras["cnpj"] = cnpj_digits
    extras["cnpj_formatted"] = format_cnpj(cnpj_digits) if len(cnpj_digits) == 14 else ""
    extras["razao_social"] = _str_field(api_json.get("razao_social"))
    extras["nome_fantasia"] = _str_field(api_json.get("nome_fantasia"))
    extras["situacao"] = _str_field(api_json.get("descricao_situacao_cadastral"))
    extras["situacao_codigo"] = _str_field(api_json.get("situacao_cadastral"))
    extras["cnae"] = _str_field(api_json.get("cnae_fiscal"))
    extras["cnae_descricao"] = _str_field(api_json.get("cnae_fiscal_descricao"))
    extras["cnaes_secundarios"] = _flatten_cnaes_secundarios(
        api_json.get("cnaes_secundarios")
    )
    extras["fiscal_tipo_logradouro"] = _str_field(
        api_json.get("descricao_tipo_de_logradouro")
    )
    extras["fiscal_logradouro"] = _str_field(api_json.get("logradouro"))
    extras["fiscal_numero"] = _str_field(api_json.get("numero"))
    extras["fiscal_complemento"] = _str_field(api_json.get("complemento"))
    extras["fiscal_bairro"] = _str_field(api_json.get("bairro"))
    extras["fiscal_cep"] = _pad_cep(api_json.get("cep"))
    extras["fiscal_municipio"] = _str_field(api_json.get("municipio"))
    extras["fiscal_uf"] = _str_field(api_json.get("uf"))
    extras["fiscal_codigo_ibge"] = _str_field(api_json.get("codigo_municipio_ibge"))
    extras["fiscal_endereco"] = build_fiscal_endereco(api_json)
    extras["natureza_juridica"] = _str_field(api_json.get("natureza_juridica"))
    extras["porte"] = _str_field(api_json.get("porte"))
    extras["matriz_filial"] = _str_field(
        api_json.get("descricao_identificador_matriz_filial")
    )
    extras["federal_phone_1"] = _str_field(api_json.get("ddd_telefone_1"))
    extras["federal_phone_2"] = _str_field(api_json.get("ddd_telefone_2"))
    extras["federal_email"] = _str_field(api_json.get("email"))
    return extras


def stamp_status(
    extras: dict[str, str],
    *,
    status: str,
    reason: str,
    scraped_at: str | None = None,
) -> dict[str, str]:
    extras["cnpj_status"] = status
    extras["cnpj_status_reason"] = reason
    extras["cnpj_scraped_at"] = scraped_at or datetime.now(timezone.utc).isoformat()
    return extras
