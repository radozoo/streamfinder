"""Normalisation for text scraped out of ČSFD markup.

Shared by the detail parser and the list parser. Both pull user-visible strings
out of HTML, and both used to keep whatever whitespace and invisible characters
the markup happened to carry — which then flowed into the database, the export
and the page. Normalise once, here, so a new call site cannot reintroduce it.
"""

import re

# Bidi isolates and embedding controls (U+2066–2069, U+202A–202E) and the
# directional marks. ČSFD wraps some episode names in these; they are invisible
# when rendered but survive .strip() and break equality checks.
_ALWAYS_INVISIBLE = re.compile(r"[⁦-⁩‪-‮‎‏]")

# Zero-width space/non-joiner/joiner. These are junk in Latin text but CARRY
# MEANING in Indic, Arabic and other complex scripts, where they control ligature
# and conjunct formation — stripping them there corrupts the word.
_ZERO_WIDTH = re.compile(r"[​‌‍]")

# Scripts that use ZWJ/ZWNJ meaningfully start above the Latin/Greek/Cyrillic
# block. If a string contains nothing from there, its zero-width characters are
# noise; if it does, leave them alone.
_COMPLEX_SCRIPT = re.compile(r"[֐-᳿ἀ-῿]")


def clean_text(value: str) -> str:
    """Collapse whitespace and drop invisible characters that carry no meaning.

    ČSFD splits headings across indented lines, so a naive get_text() carries
    newlines and tabs into storage. Zero-width characters are removed only where
    they cannot be meaningful — see _COMPLEX_SCRIPT.
    """
    out = _ALWAYS_INVISIBLE.sub("", value)
    if not _COMPLEX_SCRIPT.search(out):
        out = _ZERO_WIDTH.sub("", out)
    return re.sub(r"\s+", " ", out).strip()


def split_services(value: str) -> list[str]:
    """Split a platform/distributor label that names more than one service.

    A single ČSFD link or Distributor line occasionally carries a pair
    ("Peacock /\\n\\t\\t\\tHulu"). Left whole, the blob matches no alias and no
    brand colour, and shows up as a third platform that does not exist. No
    legitimate service name contains a slash — verified against the full
    dim_vods set.
    """
    return [part for part in (p.strip() for p in clean_text(value).split("/")) if part]
