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


def content_tokens(text: object) -> list[str]:
    """Distinct intent tokens that could plausibly name a concept: not a stop
    word, not purely numeric, at least three characters. Order preserved."""
    seen: list[str] = []
    for tok in tokenize(text):
        if len(tok) < 3 or tok.isdigit() or tok in CONTENT_STOPWORDS or tok in seen:
            continue
        seen.append(tok)
    return seen
