from jobagg.models import Job, make_job_id
from jobagg.normalize import (
    compile_tag_patterns,
    detect_language,
    extract_tech_tags,
    infer_remote_type,
    markdown_to_text,
    normalize_company,
    normalize_title,
)


def test_normalize_company_strips_legal_forms_and_case():
    assert normalize_company("Seznam.cz, a.s.") == "seznam cz"
    assert normalize_company("ACME s.r.o.") == "acme"
    assert normalize_company("Acme Digital GmbH") == "acme digital"
    assert normalize_company("Acme Ltd") == "acme"
    assert normalize_company("  Ackee   s. r. o. ") == "ackee"
    assert normalize_company("Škoda Auto a.s.") == "skoda auto"


def test_normalize_company_keeps_ordinary_words():
    assert normalize_company("Mind As One") == "mind as one"
    assert normalize_company("Coop Store") == "coop store"


def test_normalize_title_removes_gender_suffix_and_separators():
    assert normalize_title("Senior Frontend Developer (m/f/d)") == "senior frontend developer"
    assert normalize_title("Vue.js / Nuxt vývojář – Praha") == "vue.js nuxt vyvojar praha"
    assert normalize_title("Frontend Developer | React") == "frontend developer react"


def test_job_id_is_stable_across_cosmetic_differences():
    a = make_job_id("ACME s.r.o.", "Senior Frontend Developer (m/f/d)")
    b = make_job_id("acme", "senior frontend developer")
    c = make_job_id("acme", "backend developer")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_job_model_fills_id_and_collapses_whitespace():
    job = Job(source="x", source_url="http://x", title="  Vue   Dev ", company="ACME  s.r.o.")
    assert job.title == "Vue Dev"
    assert job.company == "ACME s.r.o."
    assert job.id == make_job_id("ACME s.r.o.", "Vue Dev")


def test_detect_language():
    assert detect_language("Hledáme vývojáře pro náš tým v Praze") == "cs"
    assert detect_language("Wir suchen einen Entwickler für unser Team") == "de"
    assert detect_language("We are looking for a developer to join our team") == "en"
    assert detect_language("") == "other"


def test_infer_remote_type():
    assert infer_remote_type("Vue Developer (Remote)", "Prague") == "remote"
    hybrid = infer_remote_type("Vue Developer", "Prague", "hybrid model, 2 days in office")
    assert hybrid == "hybrid"
    assert infer_remote_type("Vue Developer", "Prague", "we work on-site only") == "onsite"
    assert infer_remote_type("Vue Developer", "Prague", "", remote_flag=True) == "remote"
    assert infer_remote_type("Vue Developer", "Prague", "možnost práce z domova") == "remote"
    assert infer_remote_type("Vue Developer", "Prague") == "unknown"


def test_extract_tech_tags_uses_word_boundaries():
    patterns = compile_tag_patterns(
        {"vue": ["vue.js", "vuejs"], "nuxt": [], "typescript": ["ts"], ".net": ["c#"], "go": []}
    )
    text = "Nuxt 3 + Vue.js app in TypeScript. Backend in C#. Revenue grows. Let's go!"
    tags = extract_tech_tags(text, patterns)
    assert tags == ["vue", "nuxt", "typescript", ".net", "go"]
    assert extract_tech_tags("revenue and outsourcing", patterns) == []
    assert extract_tech_tags("stack: ts, vue", patterns) == ["vue", "typescript"]


def test_markdown_to_text():
    md = "**Role**\n\n- Build [our app](https://x.y) with `Vue`\n\n\n\n### Stack"
    assert markdown_to_text(md) == "Role\n\n- Build our app with Vue\n\nStack"


def test_parse_cz_date():
    from datetime import date, timedelta

    from jobagg.normalize import parse_cz_date

    today = date(2026, 9, 25)
    assert parse_cz_date("Přidáno dnes", today) == today
    assert parse_cz_date("Přidáno včera", today) == today - timedelta(days=1)
    assert parse_cz_date("před 3 dny", today) == date(2026, 9, 22)
    assert parse_cz_date("před 2 týdny", today) == date(2026, 9, 11)
    assert parse_cz_date("9. září", today) == date(2026, 9, 9)
    assert parse_cz_date("28. prosince", today) == date(2025, 12, 28)  # future -> last year
    assert parse_cz_date("05. 08. 2026", today) == date(2026, 8, 5)
    assert parse_cz_date("2026-09-05T10:00", today) == date(2026, 9, 5)
    assert parse_cz_date("Končí zítra", today) is None
    assert parse_cz_date(None) is None


def test_parse_salary_cz():
    from jobagg.normalize import parse_salary_cz

    assert parse_salary_cz("70 000 \u200d–\u200d 90 000 Kč") == (70000, 90000, "CZK", "month")
    assert parse_salary_cz("až 55 000 Kč / měsíc") == (None, 55000, "CZK", "month")
    assert parse_salary_cz("od 60 000 Kč") == (60000, None, "CZK", "month")
    assert parse_salary_cz("0 Kč – 130 tis. Kč") == (None, 130000, "CZK", "month")
    assert parse_salary_cz("2 500 – 3 000 EUR") == (2500, 3000, "EUR", "month")
    assert parse_salary_cz("450 Kč/hod") == (450, 450, "CZK", "hour")
    assert parse_salary_cz("$120k - $150k per year") == (120000, 150000, "USD", "year")
    assert parse_salary_cz("Odpověď do 2 týdnů") is None
    assert parse_salary_cz("") is None
