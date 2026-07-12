"""Test fixtures to ensure consistent settings across test runs.

When a `.env` file is present in the project root (e.g. with LLM_PROVIDER=ollama),
pydantic-settings auto-loads it, overriding defaults and breaking tests that mock the
Google genai.Client path. This conftest resets the critical settings to their test-safe
defaults before each test function.
"""
import pytest
from council_manager.config import settings


@pytest.fixture(autouse=True)
def reset_settings_for_tests():
    """Reset LLM provider settings to Google defaults before each test.

    This ensures that mocked tests targeting the genai.Client path aren't
    diverted through the custom provider (_generate_content_custom) path
    by a leftover .env file. No real API calls are made — the tests inject
    MagicMock clients that intercept all calls on the Google code path.
    """
    original_provider = settings.llm_provider
    original_model = settings.gemini_model
    original_api_base = settings.llm_api_base

    settings.llm_provider = "google"
    settings.gemini_model = "gemini-3.5-flash"
    settings.llm_api_base = None

    yield

    settings.llm_provider = original_provider
    settings.gemini_model = original_model
    settings.llm_api_base = original_api_base
