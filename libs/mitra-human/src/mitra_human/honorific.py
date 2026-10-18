"""How to address the caller by name: "Ravi garu", "Ravi ji", "Mr. Ravi".

The honorific follows the script of the name: a Latin-script name gets a romanised
honorific ("Ravi ji"), a Devanagari or Telugu name gets a native one ("रवि जी",
"రవి గారు").

| formality  | en                    | hi                  | te         |
|------------|-----------------------|---------------------|------------|
| friendly   | Ravi                  | Ravi                | Ravi       |
| respectful | Ravi sir / Priya ma'am| Ravi ji             | Ravi garu  |
| formal     | Mr. Ravi / Ms. Priya  | Ravi sir / Priya madam | Ravi garu |

With ``gender="unknown"`` the gendered forms fall back to the name (en) or "ji" (hi).
"""

from __future__ import annotations

from typing import Final, Literal

from mitra_human._lang import Lang, check_lang, has_devanagari, has_telugu

Formality = Literal["friendly", "respectful", "formal"]
HonorificGender = Literal["male", "female", "unknown"]

_LATIN: Final = {"ji": "ji", "garu": "garu", "sir": "sir", "madam": "madam"}
_NATIVE: Final[dict[Lang, dict[str, str]]] = {
    "en": _LATIN,
    "hi": {"ji": "जी", "sir": "सर", "madam": "मैडम"},
    "te": {"garu": "గారు"},
}


def honorific(
    name: str,
    lang: Lang,
    formality: Formality = "respectful",
    *,
    gender: HonorificGender = "unknown",
) -> str:
    """Address ``name`` the way a telecaller would at the given formality."""
    language = check_lang(lang)
    if formality not in ("friendly", "respectful", "formal"):
        raise ValueError(f"unknown formality {formality!r}")
    if gender not in ("male", "female", "unknown"):
        raise ValueError(f"unknown gender {gender!r}")
    clean = " ".join(name.split())
    if not clean:
        raise ValueError("name must not be empty")
    if formality == "friendly":
        return clean

    native = has_devanagari(clean) or has_telugu(clean)
    words = _NATIVE[language] if native else _LATIN

    if language == "en":
        if formality == "respectful":
            suffix = {"male": " sir", "female": " ma'am", "unknown": ""}[gender]
            return clean + suffix
        prefix = {"male": "Mr. ", "female": "Ms. ", "unknown": ""}[gender]
        return prefix + clean
    if language == "hi":
        if formality == "formal" and gender != "unknown":
            return f"{clean} {words['sir' if gender == 'male' else 'madam']}"
        return f"{clean} {words['ji']}"
    return f"{clean} {words['garu']}"
