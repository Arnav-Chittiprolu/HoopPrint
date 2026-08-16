from app.config import Settings
from app.services.llm import GeminiProvider, get_llm_provider


def test_get_llm_provider_none_without_key():
    settings = Settings(llm_provider="gemini", gemini_api_key="")
    assert get_llm_provider(settings) is None


def test_get_llm_provider_gemini_with_key():
    settings = Settings(llm_provider="gemini", gemini_api_key="test-key")
    provider = get_llm_provider(settings)
    assert isinstance(provider, GeminiProvider)


def test_get_llm_provider_off():
    settings = Settings(llm_provider="none", gemini_api_key="test-key")
    assert get_llm_provider(settings) is None
