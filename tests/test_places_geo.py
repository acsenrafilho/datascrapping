from types import SimpleNamespace
from unittest.mock import MagicMock

from datascrapping.scrapers.places.geo import (
    GeoValidationError,
    city_in_municipios,
    normalize_city_state,
    validate_city_state,
)


def test_normalize_city_state():
    assert normalize_city_state(" Campinas ", "sp") == ("CAMPINAS", "SP")


def test_city_in_municipios():
    municipios = [{"nome": "Campinas"}, {"nome": "Americana"}]
    assert city_in_municipios("CAMPINAS", municipios) is True
    assert city_in_municipios("SÃO PAULO", municipios) is False


def test_validate_city_state_ok():
    def fake_get(url, timeout=15):
        if "/uf/" in url:
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"sigla": "SP", "nome": "São Paulo"},
            )
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"nome": "Campinas"}, {"nome": "Americana"}],
        )

    city, state = validate_city_state("Campinas", "sp", http_get=fake_get)
    assert city == "CAMPINAS"
    assert state == "SP"


def test_validate_city_state_unknown_city():
    def fake_get(url, timeout=15):
        if "/uf/" in url:
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"sigla": "SP"},
            )
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"nome": "Campinas"}],
        )

    try:
        validate_city_state("Cidade Inventada", "SP", http_get=fake_get)
        assert False, "expected GeoValidationError"
    except GeoValidationError as exc:
        assert "não encontrada" in str(exc)


def test_validate_invalid_uf_length():
    try:
        validate_city_state("X", "SPO", http_get=MagicMock())
        assert False, "expected GeoValidationError"
    except GeoValidationError:
        pass
