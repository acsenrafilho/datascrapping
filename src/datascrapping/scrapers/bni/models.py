from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone


BNI_SEARCH_URL = "https://www.bniconnectglobal.com/web/dashboard/search"
BNI_LOGIN_URL = "https://www.bniconnectglobal.com/login"
BNI_HOME_URL = "https://www.bniconnectglobal.com/web/"

CSV_FIELDS = (
    "name",
    "company",
    "chapter",
    "city",
    "country",
    "phone",
    "email",
    "website",
    "specialty",
    "profile_url",
    "scraped_at",
)


@dataclass
class BniFilters:
    """Optional BNI search filters (country defaults to Brazil)."""

    specialty: str | None = None
    region: str | None = None
    country: str = "Brazil"
    category: str | None = None
    locale: str | None = None

    def validate(self) -> None:
        if self.locale is not None:
            from datascrapping.scrapers.bni.categories import normalize_locale

            self.locale = normalize_locale(self.locale)


@dataclass
class BniMember:
    name: str = ""
    company: str = ""
    chapter: str = ""
    city: str = ""
    country: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    specialty: str = ""
    profile_url: str = ""
    scraped_at: str = ""

    def to_row(self) -> dict[str, str]:
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()
        data = asdict(self)
        return {key: data.get(key, "") or "" for key in CSV_FIELDS}

    @classmethod
    def empty(cls) -> BniMember:
        return cls()


def filters_from_extras(extras: dict) -> BniFilters:
    region_raw = str(extras.get("region") or "").strip()
    specialty_raw = str(extras.get("specialty") or "").strip()
    category_raw = (
        str(extras["category"]).strip() if extras.get("category") else ""
    )
    locale_raw = str(extras.get("locale") or "").strip()
    filters = BniFilters(
        specialty=specialty_raw or None,
        region=region_raw or None,
        country=str(extras.get("country") or "Brazil").strip() or "Brazil",
        category=category_raw or None,
        locale=locale_raw or None,
    )
    filters.validate()
    return filters


def member_field_names() -> tuple[str, ...]:
    return tuple(f.name for f in fields(BniMember))
