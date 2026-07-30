"""Heuristic extraction tests for places.website."""

from datascrapping.scrapers.places.extract import (
    extract_from_pages,
    extract_mailto_emails,
    extract_emails_from_text,
    extract_cnpj_from_text,
    extract_social_links,
    format_cnpj,
)

HTML_CONTACT = """
<html><head><title>Audiologia Sol | Home</title></head>
<body>
  <a href="mailto:contato@audiologiasol.com.br">Fale conosco</a>
  <p>Outro: comercial@audiologiasol.com.br</p>
  <p>Tel: (11) 98888-7777</p>
  <p>CNPJ: 11.444.777/0001-61</p>
  <a href="https://www.instagram.com/audiologiasol">IG</a>
  <a href="https://facebook.com/audiologiasol">FB</a>
</body></html>
"""


def test_mailto_and_text_emails():
    mails = extract_mailto_emails(HTML_CONTACT)
    assert "contato@audiologiasol.com.br" in mails
    text_mails = extract_emails_from_text(HTML_CONTACT)
    assert "comercial@audiologiasol.com.br" in text_mails


def test_cnpj_extraction():
    cnpj = extract_cnpj_from_text(HTML_CONTACT)
    assert cnpj == "11.444.777/0001-61"
    assert format_cnpj("11444777000161") == "11.444.777/0001-61"


def test_social_hosts():
    social = extract_social_links(HTML_CONTACT)
    assert "instagram" in social
    assert "facebook" in social


def test_extract_from_pages_aggregate():
    result = extract_from_pages({"https://x.com/": HTML_CONTACT})
    assert result.emails[0] == "contato@audiologiasol.com.br"
    assert "comercial@audiologiasol.com.br" in result.emails
    assert result.cnpj_raw == "11.444.777/0001-61"
    assert result.social.get("instagram")
    assert "Audiologia Sol" in result.brand_name
    assert result.phones
