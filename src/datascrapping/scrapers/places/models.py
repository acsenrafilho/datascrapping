from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datascrapping.core.sinks import sanitize_filename

CSV_FIELDS = (
    "place_id",
    "name",
    "niche",
    "query_term",
    "city",
    "state",
    "phone",
    "phone_intl",
    "address",
    "email",
    "website",
    "lat",
    "lng",
    "maps_url",
    "rating",
    "user_ratings_total",
    "business_status",
    "types",
    "collected_at",
    "quota_units_est",
)

ENRICHED_EXTRA_FIELDS = (
    "emails_extra",
    "phones_extra",
    "cnpj_raw",
    "whatsapp",
    "whatsapp_url",
    "social_facebook",
    "social_instagram",
    "social_linkedin",
    "social_youtube",
    "social_tiktok",
    "social_twitter",
    "social_enrich_status",
    "brand_name",
    "website_status",
    "website_scraped_at",
    "pages_fetched",
    "pages_failed",
)

ENRICHED_CSV_FIELDS = CSV_FIELDS + ENRICHED_EXTRA_FIELDS

FULL_EXTRA_FIELDS = (
    "cnpj",
    "cnpj_formatted",
    "razao_social",
    "nome_fantasia",
    "situacao",
    "situacao_codigo",
    "cnae",
    "cnae_descricao",
    "cnaes_secundarios",
    "fiscal_tipo_logradouro",
    "fiscal_logradouro",
    "fiscal_numero",
    "fiscal_complemento",
    "fiscal_bairro",
    "fiscal_cep",
    "fiscal_municipio",
    "fiscal_uf",
    "fiscal_codigo_ibge",
    "fiscal_endereco",
    "natureza_juridica",
    "porte",
    "matriz_filial",
    "federal_phone_1",
    "federal_phone_2",
    "federal_email",
    "qsa_nomes",
    "qsa_qualificacoes",
    "qsa_raw",
    "cnpj_status",
    "cnpj_status_reason",
    "cnpj_scraped_at",
)

FULL_CSV_FIELDS = ENRICHED_CSV_FIELDS + FULL_EXTRA_FIELDS

DEFAULT_NICHE = "aasi"
DEFAULT_MAX_QUOTA = 20000
TERMS_PATH = Path(__file__).with_name("terms.json")


@dataclass
class PlacesSearchFilters:
    city: str
    state: str
    niche: str = DEFAULT_NICHE
    skip_geo_check: bool = False
    max_quota: int = DEFAULT_MAX_QUOTA

    def validate(self) -> None:
        if not self.city:
            raise ValueError(
                "Missing required --city for places.search / places.all"
            )
        if not self.state:
            raise ValueError(
                "Missing required --state (UF) for places.search / places.all"
            )
        if len(self.state) != 2 or not self.state.isalpha():
            raise ValueError(
                f"Invalid --state {self.state!r}; expected a 2-letter UF (e.g. SP)"
            )
        if self.max_quota < 1:
            raise ValueError("--max-quota must be a positive integer")


@dataclass
class PlaceRow:
    place_id: str = ""
    name: str = ""
    niche: str = ""
    query_term: str = ""
    city: str = ""
    state: str = ""
    phone: str = ""
    phone_intl: str = ""
    address: str = ""
    email: str = ""
    website: str = ""
    lat: str = ""
    lng: str = ""
    maps_url: str = ""
    rating: str = ""
    user_ratings_total: str = ""
    business_status: str = ""
    types: str = ""
    collected_at: str = ""
    quota_units_est: str = ""

    def to_row(self) -> dict[str, str]:
        if not self.collected_at:
            self.collected_at = datetime.now(timezone.utc).isoformat()
        # email is reserved for places.website — always empty in stage 1
        self.email = ""
        data = asdict(self)
        return {key: str(data.get(key, "") or "") for key in CSV_FIELDS}


def filters_from_extras(extras: dict[str, Any]) -> PlacesSearchFilters:
    city = str(extras.get("city") or "").strip()
    state = str(extras.get("state") or "").strip().upper()
    niche = str(extras.get("niche") or DEFAULT_NICHE).strip().lower() or DEFAULT_NICHE
    skip_geo = bool(extras.get("skip_geo_check", False))
    max_quota_raw = extras.get("max_quota", DEFAULT_MAX_QUOTA)
    try:
        max_quota = int(max_quota_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid --max-quota {max_quota_raw!r}") from exc

    filters = PlacesSearchFilters(
        city=city,
        state=state,
        niche=niche,
        skip_geo_check=skip_geo,
        max_quota=max_quota,
    )
    filters.validate()
    return filters


def run_slug(city: str, state: str, niche: str) -> str:
    city_part = sanitize_filename(city).lower().replace(" ", "_")
    city_part = re.sub(r"_+", "_", city_part).strip("_") or "city"
    return f"{city_part}_{state.lower()}_{niche.lower()}"


def load_search_terms(niche: str, terms_path: Path | None = None) -> list[str]:
    path = terms_path or TERMS_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if niche not in data:
        raise ValueError(
            f"Unknown niche {niche!r}. Known: {', '.join(sorted(data.keys()))}"
        )
    terms = data[niche]
    if not isinstance(terms, list) or not terms:
        raise ValueError(
            f"No search terms configured for niche {niche!r} "
            f"(status: failed_no_search_terms)"
        )
    return [str(t).strip() for t in terms if str(t).strip()]


def known_niches(terms_path: Path | None = None) -> list[str]:
    path = terms_path or TERMS_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    return sorted(data.keys())


@dataclass
class PlacesWebsiteFilters:
    from_path: str
    skip_llm: bool = False

    def validate(self) -> None:
        if not self.from_path:
            raise ValueError(
                "Missing required --from for places.website "
                "(path to places.csv or its parent folder)"
            )


def website_filters_from_extras(extras: dict[str, Any]) -> PlacesWebsiteFilters:
    from_path = str(extras.get("from_path") or "").strip()
    skip_llm = bool(extras.get("skip_llm", False))
    filters = PlacesWebsiteFilters(from_path=from_path, skip_llm=skip_llm)
    filters.validate()
    return filters


def resolve_places_csv(from_path: str | Path) -> Path:
    """Resolve --from to an existing places.csv file."""
    path = Path(from_path).expanduser().resolve()
    if path.is_file():
        if path.name != "places.csv":
            raise ValueError(
                f"Expected a places.csv file, got {path.name!r} ({path})"
            )
        return path
    if path.is_dir():
        candidate = path / "places.csv"
        if candidate.is_file():
            return candidate
        raise ValueError(f"No places.csv found in folder {path}")
    raise ValueError(f"Input path does not exist: {path}")


@dataclass
class PlacesCnpjFilters:
    from_path: str = ""
    cnpj: str = ""

    def validate(self) -> None:
        if not self.from_path and not self.cnpj:
            raise ValueError(
                "places.cnpj requires --from (places_enriched.csv or folder) "
                "and/or --cnpj"
            )


def cnpj_filters_from_extras(extras: dict[str, Any]) -> PlacesCnpjFilters:
    from_path = str(extras.get("from_path") or "").strip()
    cnpj = str(extras.get("cnpj") or "").strip()
    filters = PlacesCnpjFilters(from_path=from_path, cnpj=cnpj)
    filters.validate()
    return filters


def resolve_enriched_csv(from_path: str | Path) -> Path:
    """Resolve --from to an existing places_enriched.csv file."""
    path = Path(from_path).expanduser().resolve()
    if path.is_file():
        if path.name != "places_enriched.csv":
            raise ValueError(
                f"Expected a places_enriched.csv file, got {path.name!r} ({path})"
            )
        return path
    if path.is_dir():
        candidate = path / "places_enriched.csv"
        if candidate.is_file():
            return candidate
        raise ValueError(f"No places_enriched.csv found in folder {path}")
    raise ValueError(f"Input path does not exist: {path}")


def empty_enriched_extras() -> dict[str, str]:
    return {key: "" for key in ENRICHED_EXTRA_FIELDS}


def empty_full_extras() -> dict[str, str]:
    return {key: "" for key in FULL_EXTRA_FIELDS}


def base_row_from_places(row: dict[str, str]) -> dict[str, str]:
    """Copy stage-1 columns; keep email empty until enrichment fills it."""
    return {key: str(row.get(key, "") or "") for key in CSV_FIELDS}


def base_row_from_enriched(row: dict[str, str]) -> dict[str, str]:
    """Copy stage-1+2 columns for places_full.csv."""
    return {key: str(row.get(key, "") or "") for key in ENRICHED_CSV_FIELDS}


def join_extra(values: list[str], sep: str = "|") -> str:
    cleaned = [v.strip() for v in values if v and str(v).strip()]
    # preserve order, drop dupes case-insensitively for emails
    seen: set[str] = set()
    out: list[str] = []
    for item in cleaned:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return sep.join(out)
