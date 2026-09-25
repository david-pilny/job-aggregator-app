"""Text normalization helpers: company/title cleanup, language, remote type, tech tags.

Pure functions, no I/O. Kept separate from models so both adapters and the
dedup/scoring modules can import them without cycles.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

# Legal-form suffixes to strip from company names. Dotted Czech forms are matched
# with their dots so ordinary words like "as" are left alone.
_COMPANY_SUFFIX_RE = re.compile(
    r"""
    (?<![\w.])
    (?:
        s\.\s?r\.\s?o\.? | spol\.\s?s\s?r\.\s?o\.? | a\.\s?s\.? | k\.\s?s\.? | v\.\s?o\.\s?s\.?
        | z\.\s?s\.? | o\.\s?p\.\s?s\.? | z\.\s?u\.? | s\.\s?p\.?
        | sro | gmbh | ag | ug | kg | ltd\.? | limited | inc\.? | llc | corp\.? | corporation
        | plc | b\.?v\.? | n\.?v\.? | s\.?a\.? | s\.?r\.?l\.? | sp\.\s?z\s?o\.\s?o\.? | oy | ab | se
        | group | holding
    )
    (?![\w.])
    """,
    re.IGNORECASE | re.VERBOSE,
)
_TITLE_NOISE_RE = re.compile(
    r"""
    \(\s*[mfwdxz/\s]{3,9}\s*\)      # (m/f/d), (m/w/d), (m/z) ...
    | \b[mfw]/[fwmd](?:/[dx])?\b    # m/f/d without parentheses
    | \b(?:all\s+genders|w/m/d)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NON_WORD_RE = re.compile(r"[^\w\s+#.]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def normalize_company(name: str) -> str:
    text = strip_accents(name).lower()
    text = _COMPANY_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[,;:()\"'’]", " ", text)
    text = re.sub(r"[.&\-]", " ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    text = strip_accents(title).lower()
    text = _TITLE_NOISE_RE.sub(" ", text)
    text = re.sub(r"[/|,()\[\]\-–—:]", " ", text)
    text = _NON_WORD_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def collapse_ws(text: str | None) -> str:
    return _WS_RE.sub(" ", text or "").strip()


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_MARK_RE = re.compile(r"[*_`#>]{1,3}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def markdown_to_text(text: str | None) -> str:
    """Cheap markdown/HTML -> plain text good enough for keyword matching and digests."""
    if not text:
        return ""
    out = _HTML_TAG_RE.sub(" ", text)
    out = _MD_LINK_RE.sub(r"\1", out)
    out = _MD_MARK_RE.sub("", out)
    out = re.sub(r"\\([\\*_#\-])", r"\1", out)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"^[ \t]+", "", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# --- language ----------------------------------------------------------------

_LANG_WORDS: dict[str, frozenset[str]] = {
    "cs": frozenset(
        "a na pro se je jsme jsou nebo aby jak co ve od do za hledame hledáme nabizime "
        "nabízíme prace práce vyvojar vývojář vyvojare "
        "vývojáře tym tým znalost zkusenosti zkušenosti pozice "
        "nabidka nabídka mzda plat cestina čeština firma spolecnost "
        "společnost".split()
    ),
    "de": frozenset(
        "und der die das wir sie mit für fur ist nicht ein eine bei zu von auf werden "
        "entwickler entwicklerin stelle unternehmen kenntnisse erfahrung suchen bieten team "
        "gehalt deutsch arbeit".split()
    ),
    "en": frozenset(
        "the and you we with for our are your will this team experience developer engineer "
        "skills work role about looking join years salary english remote".split()
    ),
}
# Only letters that are distinctive for Czech; á/é/í/ú also occur in French, Spanish etc.
_CS_CHARS = set("ěščřžýůťďň"
                "ĚŠČŘŽÝŮŤĎŇ")
_DE_CHARS = set("äöüßÄÖÜ")
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(*texts: str | None) -> str:
    """Heuristic cs/en/de detection. Returns 'other' when there is no signal."""
    text = " ".join(t for t in texts if t)
    if not text.strip():
        return "other"
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    scores = {lang: 0.0 for lang in _LANG_WORDS}
    for tok in tokens:
        for lang, words in _LANG_WORDS.items():
            if tok in words:
                scores[lang] += 1
    scores["cs"] += sum(1 for ch in text if ch in _CS_CHARS) * 0.5
    scores["de"] += sum(1 for ch in text if ch in _DE_CHARS) * 0.5
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "other"


# --- remote type -------------------------------------------------------------

_HYBRID_RE = re.compile(r"\bhybrid|hybridn[ií]|hybridn[eě]", re.IGNORECASE)
_REMOTE_RE = re.compile(
    r"\b(?:fully\s+)?remote\b|\bremotely\b|work\s+from\s+home|\bwfh\b|home[\s-]?office"
    r"|z\s+domova|na\s+d[aá]lku|vzd[aá]len[eě]|pr[aá]ce\s+z\s+domu"
    r"|distributed\s+team",
    re.IGNORECASE,
)
_ONSITE_RE = re.compile(
    r"\bon[\s-]?site\b|\bin[\s-]office\b|v\s+kancel[aá][rř]i|\bno\s+remote\b"
    r"|\bvor\s+ort\b",
    re.IGNORECASE,
)


def infer_remote_type(
    title: str | None,
    location: str | None,
    description: str | None = None,
    remote_flag: bool | None = None,
) -> str:
    """Best-effort remote/hybrid/onsite from free text plus an optional source flag.

    Priority: explicit 'hybrid' > explicit remote wording in title/location >
    source flag > description wording > on-site wording > unknown.
    """
    head = f"{title or ''} {location or ''}"
    body = description or ""
    if _HYBRID_RE.search(head) or _HYBRID_RE.search(body):
        return "hybrid"
    if _REMOTE_RE.search(head):
        return "remote"
    if remote_flag:
        return "remote"
    if _REMOTE_RE.search(body):
        return "remote"
    if _ONSITE_RE.search(head) or _ONSITE_RE.search(body):
        return "onsite"
    return "unknown"


# --- Czech dates and salaries ------------------------------------------------

_CZ_MONTHS = {
    "leden": 1, "ledna": 1, "unor": 2, "unora": 2, "brezen": 3, "brezna": 3, "duben": 4,
    "dubna": 4, "kveten": 5, "kvetna": 5, "cerven": 6, "cervna": 6, "cervenec": 7,
    "cervence": 7, "srpen": 8, "srpna": 8, "zari": 9, "rijen": 10, "rijna": 10,
    "listopad": 11, "listopadu": 11, "prosinec": 12, "prosince": 12,
}


def parse_cz_date(text: str | None, today: date | None = None) -> date | None:
    """Parse Czech relative/absolute dates: 'dnes', 'včera', 'před 3 dny',
    '9. září', '05. 08. 2026', '2026-09-05'. Returns None when unsure."""
    if not text:
        return None
    today = today or date.today()
    t = strip_accents(text).lower()
    if re.search(r"\b(dnes|nova nabidka|new)\b", t):
        return today
    if "vcera" in t or "yesterday" in t:
        return today - timedelta(days=1)
    m = re.search(r"pred\s+(\d+)\s+(dny|dnem|tydn\w*|hod\w*)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("hod"):
            return today
        return today - timedelta(days=n * (7 if unit.startswith("tydn") else 1))
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", t)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(\d{1,2})\.\s*([a-z]+)(?:\s+(\d{4}))?", t)
    if m and m.group(2) in _CZ_MONTHS:
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = date(year, _CZ_MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
        if not m.group(3) and d > today + timedelta(days=7):
            d = d.replace(year=year - 1)
        return d
    return None


_SALARY_NUM_RE = re.compile(r"(\d{1,3}(?:[   .]\d{3})+|\d+(?:[.,]\d+)?)\s*(tis\.?|k\b)?", re.I)
_ZW_RE = re.compile(r"[​‌‍⁠﻿]")


def parse_salary_cz(text: str | None) -> tuple[float | None, float | None, str, str] | None:
    """Parse salary strings like '70 000 – 90 000 Kč', 'až 55 000 Kč / měsíc',
    'od 60 000 Kč', '0 Kč – 130 tis. Kč', '2 500 EUR'. Returns
    (min, max, currency, period) or None when no currency/number is found."""
    if not text:
        return None
    t = _ZW_RE.sub("", text).replace(" ", " ")
    low = strip_accents(t).lower()
    if "kc" in low or "czk" in low:
        currency = "CZK"
    elif "eur" in low or "€" in t:
        currency = "EUR"
    elif "usd" in low or "$" in t:
        currency = "USD"
    else:
        return None
    if re.search(r"hod|hour|/\s*h\b", low):
        period = "hour"
    elif re.search(r"rok|year|annum|p\.a\.", low):
        period = "year"
    elif re.search(r"den|day", low):
        period = "day"
    else:
        period = "month"
    values: list[float] = []
    for num, thousands in _SALARY_NUM_RE.findall(t):
        cleaned = re.sub(r"[   ]", "", num)
        if "." in cleaned and len(cleaned.split(".")[-1]) == 3:
            cleaned = cleaned.replace(".", "")
        try:
            value = float(cleaned.replace(",", "."))
        except ValueError:
            continue
        if thousands:
            value *= 1000
        values.append(value)
    if not values or not any(v > 0 for v in values):
        return None
    if len(values) >= 2:
        lo, hi = min(values[:2]), max(values[:2])
        return (lo or None), (hi or None), currency, period  # "0 Kč – 130 tis." => up to
    single = values[0]
    if re.search(r"\b(od|from|min)\b", low):
        return single, None, currency, period
    if re.search(r"\b(az|do|up to|max)\b", low):
        return None, single, currency, period
    return single, single, currency, period


# --- tech tags ---------------------------------------------------------------


def compile_tag_patterns(dictionary: Mapping[str, Iterable[str]]) -> dict[str, re.Pattern[str]]:
    """Build one regex per tag from its synonyms; boundaries avoid 'vue' in 'revenue'."""
    compiled: dict[str, re.Pattern[str]] = {}
    for tag, synonyms in dictionary.items():
        alts = sorted({s.lower() for s in [tag, *synonyms]}, key=len, reverse=True)
        pattern = "|".join(re.escape(a) for a in alts)
        compiled[tag] = re.compile(rf"(?<![\w+#])(?:{pattern})(?![\w+#])", re.IGNORECASE)
    return compiled


def extract_tech_tags(text: str, patterns: Mapping[str, re.Pattern[str]]) -> list[str]:
    return [tag for tag, rx in patterns.items() if rx.search(text)]
