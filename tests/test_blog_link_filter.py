from datascrapping.scrapers.blog.communicare import classify_communicare
from datascrapping.scrapers.blog.essencial import classify_essencial
from datascrapping.scrapers.blog.otoclinic import classify_otoclinic


BASE_COMMUNICARE = "https://comunicareaparelhosauditivos.com/blog/"


def test_communicare_accepts_blog_slug():
    ok, reason = classify_communicare(
        BASE_COMMUNICARE,
        "https://comunicareaparelhosauditivos.com/blog/perda-auditiva/",
    )
    assert ok is True
    assert reason == "ok_blog_slug"


def test_communicare_rejects_pagination():
    ok, reason = classify_communicare(
        BASE_COMMUNICARE,
        "https://comunicareaparelhosauditivos.com/blog/page/2/",
    )
    assert ok is False
    assert reason in {"rota_bloqueada", "paginacao_blog"}


def test_essencial_accepts_root_slug():
    ok, reason = classify_essencial(
        "https://www.essencialaparelhosauditivos.com/blog/",
        "https://www.essencialaparelhosauditivos.com/aparelho-auditivo/",
    )
    assert ok is True
    assert reason == "ok_slug_raiz"


def test_otoclinic_rejects_monthly_archive():
    ok, reason = classify_otoclinic(
        "https://otoclinic.com.br/blog-otoclinic/",
        "https://otoclinic.com.br/2024/03/",
    )
    assert ok is False
    assert reason == "arquivo_mensal"
