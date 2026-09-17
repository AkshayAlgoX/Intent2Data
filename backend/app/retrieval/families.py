"""Structural (cross-wave) variable families.

HRS repeats the same item in every biennial wave under a wave-prefixed code
(JD112 / KD112 / LD112 ...). A *family* groups those copies so that a concept
found once inside a retrieved module can be completed across waves
deterministically. This is a runtime-safe reimplementation of the family key
used by the validated offline experiments; it uses only codebook fields.
"""

import re

WAVE_PREFIX_YEAR = {
    "H": "2002", "J": "2004", "K": "2006", "L": "2008", "M": "2010", "N": "2012",
    "O": "2014", "P": "2016", "Q": "2018", "R": "2020", "S": "2022",
}
_LABEL_PREFIX = re.compile(r"^\s*Q?\d+[A-Z]?(?:_[A-Z0-9]+)?[.:]\s*")
_LABEL_TOKENS = re.compile(r"[A-Z0-9]+")
_LABEL_STOP = {"WAY", "YOU", "FEEL", "SERIOUS"}
_COGNITION = re.compile(r"^([RS])(\d+)(.+)$")
_WS = re.compile(r"\s+")


def normalize_code(code: object) -> str:
    return _WS.sub("", str(code)).upper()


def family_key(record: dict) -> str:
    code = normalize_code(record.get("variable_code", ""))
    product_family = str(record.get("product_family", ""))
    year = str(record.get("year", ""))
    section = record.get("section", "")
    if (
        product_family in {"core", "exit"}
        and len(code) >= 3
        and code[0] in WAVE_PREFIX_YEAR
        and WAVE_PREFIX_YEAR[code[0]] == year
    ):
        label = str(record.get("variable_label", "")).upper()
        label = _LABEL_PREFIX.sub("", label).replace("#", " NUM ")
        tokens = [t for t in _LABEL_TOKENS.findall(label) if t not in _LABEL_STOP]
        semantic = "L-" + "-".join(tokens[:16])
        if len(semantic) >= 5:
            return f"HRS::{product_family}::{section}::label::{semantic}"
        return f"HRS::{product_family}::{section}::code::{code[1:]}"
    if product_family == "cognition":
        match = _COGNITION.match(code)
        if match:
            suffix = re.sub(r"[PW]$", "", match.group(3))
            return f"HRS::cognition::{match.group(1).lower()}::{suffix.lower()}"
    return f"HRS::{record.get('product_key', '')}::{section}::{code}"
