"""Optional Gemini enrichment for places.website (Poetry extra: llm)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from datascrapping.scrapers.places.crawl import extract_text_from_html

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema_website.json")
DEFAULT_MODEL = "gemini-2.5-flash-lite"
PER_PAGE_TEXT_LIMIT = 20_000
TOTAL_TEXT_LIMIT = 300_000


class GeminiUnavailable(Exception):
    """Raised when the llm extra / API key / call is not usable."""


def load_schema(path: Path | None = None) -> dict[str, Any]:
    schema_path = path or SCHEMA_PATH
    return json.loads(schema_path.read_text(encoding="utf-8"))


def build_combined_text(pages: dict[str, str]) -> str:
    chunks: list[str] = []
    for url, html in pages.items():
        text = extract_text_from_html(html)
        if text:
            chunks.append(f"=== Page: {url} ===\n{text[:PER_PAGE_TEXT_LIMIT]}")
    return "\n\n".join(chunks)[:TOTAL_TEXT_LIMIT]


def build_prompt(combined_text: str) -> str:
    return f"""Analyze the following website content and extract structured company information in Brazilian Portuguese context.

Website Content:
{combined_text}

Extract and return ONLY the following information in JSON format (return null for missing fields):

1. **brand_name**: The official company brand name
2. **emails**: All email addresses found (contact, vendas, etc.)
3. **addresses**: All physical addresses found (parse into structured components: street, number, district, city, state, postal_code)
4. **phones**: All phone numbers (up to 4), classify type as: 'fixed', 'mobile', 'whatsapp', 'fax', or 'other'
5. **history**: Brief company history or about section (max 1500 characters)
6. **products**: List of main products offered
7. **services**: List of main services offered
8. **brands**: List of product brands sold or represented
9. **social_links**: Social media URLs (facebook, instagram, youtube, tiktok, linkedin, twitter, others)
10. **cnpj**: Brazilian company ID (CNPJ) in format XX.XXX.XXX/XXXX-XX if found
11. **offers_summary**: Summary of current offers or promotions (max 1500 characters)

Guidelines:
- Extract information in Brazilian Portuguese
- For addresses: identify street type (Rua, Av., etc.), number, district, city, state abbreviation (SP, RJ, etc.), CEP
- For phones: detect type based on context (WhatsApp, Celular, Fixo, etc.) or digit count (9 digits = mobile)
- Social links: extract full URLs
- Return null for any field that cannot be found
- Be concise and accurate

Return ONLY valid JSON following the schema provided."""


def extract_with_gemini(
    pages: dict[str, str],
    api_key: str,
    model_name: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Call Gemini with JSON schema. Fail-soft callers should catch exceptions."""
    if not api_key:
        raise GeminiUnavailable("Missing GEMINI_API_KEY")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise GeminiUnavailable(
            "google-generativeai not installed; "
            "run: poetry install -E llm"
        ) from exc

    combined = build_combined_text(pages)
    if not combined.strip():
        return {}

    schema = load_schema()
    prompt = build_prompt(combined)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    logger.info("Calling Gemini (%s) for website enrichment", model_name)
    result = model.generate_content(prompt)
    text = getattr(result, "text", None) or ""
    if not text.strip():
        return {}
    return json.loads(text)
