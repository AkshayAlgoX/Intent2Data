import re

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: object) -> list[str]:
    """Same tokenizer the validated retrieval experiments used, so runtime
    module rankings reproduce the offline measurements."""
    if not isinstance(text, str):
        return []
    return _TOKEN.findall(text.lower())
