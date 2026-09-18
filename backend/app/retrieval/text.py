import re

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: object) -> list[str]:
    """Same tokenizer the validated retrieval experiments used, so runtime
    module rankings reproduce the offline measurements."""
    if not isinstance(text, str):
        return []
    return _TOKEN.findall(text.lower())


# Function words that carry no retrievable concept. Used only to decide which
# intent tokens count as "concept terms" for the coverage signal.
CONTENT_STOPWORDS = frozenset("""
the a an of in on to and or is are be with by for from at as into over under after before during between among
does do did how could might can may there what whether which who whom this that these those it its their his her
relate related relationship associated association affect affects affecting predict predicts predicting shape shapes
drive drives influence influences impact impacts connected linked contribute contributes later life older adults
""".split())


_COMPOUND = re.compile(r"\b([A-Za-z]+\d+(?:\.\d+)?|[A-Za-z]+-\d+[A-Za-z0-9]*)\b")


def concept_terms(text: object) -> list[tuple[str, list[str]]]:
    """Concept terms for the coverage report: (surface form, index tokens).

    Scientific compounds such as "PM2.5", "COVID-19" or "HbA1c" are reported
    in their surface form so the report is readable, while matching uses the
    same alphanumeric tokens the module index was built from (the index
    tokenizer splits "PM2.5" into ["pm2", "5"]; the digit-only part is dropped
    because it carries no concept). Everything else follows content_tokens()."""
    if not isinstance(text, str):
        return []
    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    covered: set[str] = set()
    for m in _COMPOUND.finditer(text):
        surface = m.group(1).lower()
        parts = [t for t in tokenize(surface) if len(t) >= 3 and not t.isdigit() and t not in CONTENT_STOPWORDS]
        if parts and surface not in seen:
            seen.add(surface); covered.update(tokenize(surface))
            out.append((surface, parts))
    for tok in content_tokens(text):
        if tok in covered or tok in seen:
            continue
        seen.add(tok)
        out.append((tok, [tok]))
    return out


def content_tokens(text: object) -> list[str]:
    """Distinct intent tokens that could plausibly name a concept: not a stop
    word, not purely numeric, at least three characters. Order preserved."""
    seen: list[str] = []
    for tok in tokenize(text):
        if len(tok) < 3 or tok.isdigit() or tok in CONTENT_STOPWORDS or tok in seen:
            continue
        seen.append(tok)
    return seen
