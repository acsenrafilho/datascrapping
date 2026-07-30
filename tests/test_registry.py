from datascrapping.core.registry import ScraperRegistry
from datascrapping.core.base import BaseScraper, ScrapeContext, ScrapeResult


class DummyScraper(BaseScraper):
    name = "dummy.test"
    description = "dummy"

    def run(self, ctx: ScrapeContext) -> ScrapeResult:
        return ScrapeResult(scraper=self.name, message="ok")


def test_registry_register_and_list():
    reg = ScraperRegistry()
    reg.register(DummyScraper)
    assert reg.names() == ["dummy.test"]
    assert reg.list() == [("dummy.test", "dummy")]
    assert reg.get("dummy.test") is DummyScraper


def test_registry_unknown_raises():
    reg = ScraperRegistry()
    try:
        reg.get("missing")
        assert False, "expected KeyError"
    except KeyError as exc:
        assert "missing" in str(exc)


def test_load_scrapers_registers_expected_names():
    from datascrapping.core.registry import registry
    from datascrapping.scrapers.loader import load_scrapers

    load_scrapers()
    names = set(registry.names())
    expected = {
        "blog.auditik",
        "blog.communicare",
        "blog.concorrente",
        "blog.essencial",
        "blog.otoclinic",
        "blog.sonorita",
        "blog.all",
        "bni",
        "places.search",
        "places.website",
        "places.cnpj",
    }
    assert expected.issubset(names)
