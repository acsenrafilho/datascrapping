"""Gemini helper unit tests (no real API)."""

from unittest.mock import MagicMock, patch

import pytest

from datascrapping.scrapers.places.gemini import (
    GeminiUnavailable,
    build_combined_text,
    extract_with_gemini,
    load_schema,
)


def test_load_schema_has_emails():
    schema = load_schema()
    assert "emails" in schema["properties"]
    assert "cnpj" in schema["properties"]


def test_build_combined_text():
    pages = {
        "https://a.com/": "<html><body><p>hello clinic</p></body></html>",
    }
    text = build_combined_text(pages)
    assert "Page: https://a.com/" in text
    assert "hello clinic" in text


def test_extract_requires_key():
    with pytest.raises(GeminiUnavailable):
        extract_with_gemini({"https://a.com/": "<p>hi</p>"}, api_key="")


def test_extract_missing_package():
    import builtins

    real_import = builtins.__import__

    def blocker(name, *args, **kwargs):
        if name == "google.generativeai" or (
            name == "google" and args and args[2] and "generativeai" in args[2]
        ):
            raise ImportError("no package")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=blocker):
        with pytest.raises(GeminiUnavailable) as exc:
            extract_with_gemini({"https://a.com/": "<p>hi</p>"}, api_key="k")
    assert "llm" in str(exc.value).lower()


def test_extract_parses_json_response():
    fake_genai = MagicMock()
    model = MagicMock()
    model.generate_content.return_value = MagicMock(
        text='{"brand_name": "X", "emails": ["a@b.com"]}'
    )
    fake_genai.GenerativeModel.return_value = model

    google_pkg = MagicMock()
    google_pkg.generativeai = fake_genai

    with (
        patch.dict(
            "sys.modules",
            {"google": google_pkg, "google.generativeai": fake_genai},
        ),
        patch(
            "datascrapping.scrapers.places.gemini.build_combined_text",
            return_value="content",
        ),
    ):
        data = extract_with_gemini(
            {"https://a.com/": "<p>x</p>"},
            api_key="k",
        )

    assert data.get("brand_name") == "X"
    assert data.get("emails") == ["a@b.com"]
    fake_genai.configure.assert_called_once_with(api_key="k")
