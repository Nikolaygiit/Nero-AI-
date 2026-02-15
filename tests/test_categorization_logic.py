import pytest
import unittest.mock
from unittest.mock import MagicMock, AsyncMock
import sys
import asyncio

# Mock dependencies to avoid import errors
sys.modules['database'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['httpx'] = MagicMock()

# Now we can import the service
from services.gemini import GeminiService

def test_get_categorized_models_caching():
    async def run_test():
        service = GeminiService()

        # Define some mock models
        mock_models = [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro-vision",
            "imagen-3.0"
        ]

        # Mock list_available_models
        service.list_available_models = AsyncMock(return_value=mock_models)

        # First call - should categorize
        text_models1, image_models1 = await service.get_categorized_models()

        assert "gemini-1.5-pro" in text_models1['pro']
        assert "gemini-1.5-flash" in text_models1['flash']
        assert "imagen-3.0" in image_models1['medium'] # Based on logic, imagen-3.0 falls to medium unless specific keywords present

        # Check if caching attributes are set
        assert service._categorized_models_cache is not None
        assert service._last_models_ref is mock_models

        # Second call - should return cached result
        # To verify it uses cache, we can check if it returns the exact same object

        text_models2, image_models2 = await service.get_categorized_models()

        assert text_models1 is text_models2
        assert image_models1 is image_models2

        # Verify list_available_models was called twice (it's called inside get_categorized_models)
        assert service.list_available_models.call_count == 2

        # Now simulate a change in models (different list object)
        new_mock_models = ["gemini-2.0-pro"]
        service.list_available_models = AsyncMock(return_value=new_mock_models)

        text_models3, image_models3 = await service.get_categorized_models()

        assert text_models3 is not text_models1
        assert "gemini-2.0-pro" in text_models3['pro']
        assert service._last_models_ref is new_mock_models

    asyncio.run(run_test())

def test_categorization_logic_correctness():
    async def run_test():
        service = GeminiService()

        mock_models = [
            "gemini-3-pro-image",          # premium
            "gemini-4.0-ultra-image",      # premium
            "imagen-4.0-generate",         # high (changed from gemini-4.0-generate to satisfy 'imagen' check)
            "gemini-2.5-flash-image-preview", # high
            "imagen-3.0",                  # medium
            "gemini-1.5-pro",              # text pro
            "gemini-1.5-flash",            # text flash
            "gemini-1.0-pro"               # text pro
        ]

        service.list_available_models = AsyncMock(return_value=mock_models)

        text_models, image_models = await service.get_categorized_models()

        # Check Image Models
        assert "gemini-3-pro-image" in image_models['premium']
        assert "gemini-4.0-ultra-image" in image_models['premium']
        assert "imagen-4.0-generate" in image_models['high']
        assert "gemini-2.5-flash-image-preview" in image_models['high']
        assert "imagen-3.0" in image_models['medium']

        # Check Text Models
        assert "gemini-1.5-pro" in text_models['pro']
        assert "gemini-1.0-pro" in text_models['pro']
        assert "gemini-1.5-flash" in text_models['flash']

    asyncio.run(run_test())
