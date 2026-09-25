"""Text normalization helpers: company/title cleanup, language, remote type, tech tags.

Pure functions, no I/O. Kept separate from models so both adapters and the
dedup/scoring modules can import them without cycles.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

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
