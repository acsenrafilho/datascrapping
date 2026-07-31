"""Unit tests for BrasilAPI CNPJ client and field mapping."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import requests

from datascrapping.scrapers.places.federal import (
    build_fiscal_endereco,
    fetch_cnpj,
    flatten_qsa,
    map_federal_to_row,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "places" / "cnpj_ativa.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_map_federal_to_row_success():
    data = _load_fixture()
    row = map_federal_to_row(data)
    assert row["cnpj"] == "19131243000197"
    assert row["cnpj_formatted"] == "19.131.243/0001-97"
    assert row["razao_social"] == "OPEN KNOWLEDGE BRASIL"
    assert row["nome_fantasia"] == "OKBR"
    assert row["situacao"] == "ATIVA"
    assert row["situacao_codigo"] == "2"
    assert row["cnae"] == "9430800"
    assert "associações" in row["cnae_descricao"].lower() or "associacoes" in row[
        "cnae_descricao"
    ].lower() or row["cnae_descricao"]
    assert "6201501:" in row["cnaes_secundarios"]
    assert row["fiscal_uf"] == "SP"
    assert row["fiscal_cep"] == "01153000"
    assert row["federal_phone_1"] == "1133334444"
    assert row["federal_email"] == ""
    assert row["qsa_nomes"] == "MARIA SILVA|JOAO SOUZA"
    assert row["qsa_qualificacoes"] == "Sócio-Administrador|Sócio"
    assert "MARIA SILVA:Sócio-Administrador" in row["qsa_raw"]
    assert "SAO PAULO" in row["fiscal_endereco"]
    assert "CEP 01153000" in row["fiscal_endereco"]


def test_flatten_qsa_empty():
    assert flatten_qsa(None) == ("", "", "")
    assert flatten_qsa([]) == ("", "", "")
    assert flatten_qsa("bad") == ("", "", "")


def test_map_federal_none_returns_empty():
    row = map_federal_to_row(None)
    assert row["razao_social"] == ""
    assert row["cnpj"] == ""
    assert row["qsa_nomes"] == ""
    assert row["qsa_raw"] == ""


def test_build_fiscal_endereco():
    addr = build_fiscal_endereco(_load_fixture())
    assert addr.startswith("RUA VITORINO CARMILO, 498")
    assert "BARRA FUNDA" in addr
    assert "SAO PAULO/SP" in addr


def test_fetch_cnpj_200(monkeypatch):
    data = _load_fixture()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = data
    session = MagicMock()
    session.get.return_value = response

    result = fetch_cnpj("19131243000197", session=session, sleep_fn=lambda _: None)
    assert result.status == "completed"
    assert result.data == data
    assert "Successfully" in result.reason


def test_fetch_cnpj_404(monkeypatch):
    response = MagicMock()
    response.status_code = 404
    session = MagicMock()
    session.get.return_value = response

    result = fetch_cnpj("00000000000000", session=session, sleep_fn=lambda _: None)
    assert result.status == "completed"
    assert result.data is None
    assert "not found" in result.reason.lower()


def test_fetch_cnpj_429_then_fail():
    response = MagicMock()
    response.status_code = 429
    session = MagicMock()
    session.get.return_value = response

    result = fetch_cnpj("19131243000197", session=session, sleep_fn=lambda _: None)
    assert result.status == "failed"
    assert "rate limit" in result.reason.lower()
    assert session.get.call_count == 3  # initial + 2 retries


def test_fetch_cnpj_other_http_no_retry():
    response = MagicMock()
    response.status_code = 500
    response.text = "err"
    session = MagicMock()
    session.get.return_value = response

    result = fetch_cnpj("19131243000197", session=session, sleep_fn=lambda _: None)
    assert result.status == "failed"
    assert "HTTP 500" in result.reason
    assert session.get.call_count == 1


def test_fetch_cnpj_timeout_retries():
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ReadTimeout("slow")

    result = fetch_cnpj("19131243000197", session=session, sleep_fn=lambda _: None)
    assert result.status == "failed"
    assert "timeout" in result.reason.lower()
    assert session.get.call_count == 3
