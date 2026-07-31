"""Heuristic extraction tests for places.website."""

from datascrapping.scrapers.places.extract import (
    extract_from_pages,
    extract_mailto_emails,
    extract_emails_from_text,
    extract_cnpj_from_text,
    extract_social_links,
    extract_tel_links,
    extract_whatsapp_from_html,
    extract_contacts_from_html,
    format_cnpj,
    normalize_whatsapp_digits,
)

HTML_CONTACT = """
<html><head><title>Audiologia Sol | Home</title></head>
<body>
  <a href="mailto:contato@audiologiasol.com.br">Fale conosco</a>
  <p>Outro: comercial@audiologiasol.com.br</p>
  <p>Tel: (11) 98888-7777</p>
  <a href="tel:+5511999887766">Ligar</a>
  <a href="https://wa.me/5511988887777">WhatsApp</a>
  <p>CNPJ: 11.444.777/0001-61</p>
  <a href="https://www.instagram.com/audiologiasol">IG</a>
  <a href="https://facebook.com/audiologiasol">FB</a>
</body></html>
"""

HTML_WA_API = """
<a href="https://api.whatsapp.com/send?phone=5516999123456&text=Oi">WA</a>
"""

HTML_SOCIAL_META = """
<html><head>
  <meta property="og:description" content="Clínica AASI. Contato: bio@clinica.com.br ou wa.me/551633334444" />
  <meta property="og:title" content="Clinica Exemplo" />
</head><body>Login to continue</body></html>
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


def test_whatsapp_wa_me():
    digits, url = extract_whatsapp_from_html(HTML_CONTACT)
    assert digits == "5511988887777"
    assert "wa.me" in url


def test_whatsapp_api_send():
    digits, url = extract_whatsapp_from_html(HTML_WA_API)
    assert digits == "5516999123456"


def test_normalize_whatsapp_local_ddd():
    assert normalize_whatsapp_digits("16999123456") == "5516999123456"
    assert normalize_whatsapp_digits("5516999123456") == "5516999123456"


def test_tel_links():
    phones = extract_tel_links(HTML_CONTACT)
    assert any("5511999887766" in p.replace(" ", "").replace("+", "") for p in phones)


def test_extract_from_pages_aggregate():
    result = extract_from_pages({"https://x.com/": HTML_CONTACT})
    assert result.emails[0] == "contato@audiologiasol.com.br"
    assert "comercial@audiologiasol.com.br" in result.emails
    assert result.cnpj_raw == "11.444.777/0001-61"
    assert result.social.get("instagram")
    assert "Audiologia Sol" in result.brand_name
    assert result.phones
    assert result.whatsapp == "5511988887777"


def test_contacts_from_social_meta():
    contacts = extract_contacts_from_html(HTML_SOCIAL_META)
    assert "bio@clinica.com.br" in [e.lower() for e in contacts["emails"]]
    assert contacts["whatsapp"] == "551633334444"
