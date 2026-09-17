"""Provider registry. Core orchestration only ever sees LLMClient.

The default is the offline stand-in; a live provider is used only when
INTENT2DATA_LLM_PROVIDER names it explicitly. Provider SDKs are imported
inside their adapter modules, never here.
"""

from app.llm.client import LLMClient, StaticLLMClient
from app.llm.offline import OfflineLexicalLLMClient


class ProviderNotAvailable(RuntimeError):
    pass


def build_llm_client(provider: str, model: str = "") -> LLMClient:
    name = (provider or "offline").strip().lower()
    if name == "offline":
        return OfflineLexicalLLMClient()
    if name == "static":
        return StaticLLMClient()
    if name == "gemini":
        from app.llm.gemini import GeminiClient  # adapter owns the SDK import
        return GeminiClient(model=model or None)   # raises LLMConfigError if the key is missing
    raise ProviderNotAvailable(f"LLM provider {provider!r} is not available in this build")
