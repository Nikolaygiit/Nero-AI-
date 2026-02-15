import sys
from unittest.mock import MagicMock, AsyncMock
import asyncio

# --- Mocking external dependencies BEFORE import ---
sys.modules['httpx'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy.ext.asyncio'] = MagicMock()
sys.modules['pydantic'] = MagicMock()
sys.modules['pydantic_settings'] = MagicMock()
sys.modules['structlog'] = MagicMock()
sys.modules['telegram'] = MagicMock()
sys.modules['telegram.ext'] = MagicMock()
sys.modules['telegram.error'] = MagicMock()

# Mock config
mock_config = MagicMock()
mock_config.GEMINI_API_KEY = "test_key"
mock_config.GEMINI_API_BASE = "http://test.api"
# Need to mock constants used in image_gen.py
mock_config.IMAGE_STYLES = {}
mock_config.IMAGE_SIZES = {}
sys.modules['config'] = mock_config

# Mock database
mock_db = MagicMock()
mock_db.update_stats = AsyncMock()
# Since database module usually exposes 'db' object
mock_db_module = MagicMock()
mock_db_module.db = mock_db
sys.modules['database'] = mock_db_module

# --- End of Mocks ---

import pytest
import base64
from unittest.mock import patch

# Now import the class to test
# This should now work because deps are mocked
from services.image_gen import ArtemoxImageGenerator

def test_artemox_generate_with_image():
    """Тест генерации изображения с исходным изображением (img2img)"""
    asyncio.run(_test_artemox_generate_with_image_async())

async def _test_artemox_generate_with_image_async():
    # We need to patch httpx.AsyncClient because it is used inside the method
    # Even though we mocked the module, we want to control the return value of AsyncClient() context manager

    # Get the mocked httpx module
    mock_httpx = sys.modules['httpx']

    # Create a mock for the client instance
    mock_client_instance = AsyncMock()

    # Setup context manager behavior
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.__aexit__.return_value = None

    # Setup post method response
    mock_response = MagicMock()
    mock_response.status_code = 200
    fake_image_bytes = b"fake_image_data"
    fake_b64 = base64.b64encode(fake_image_bytes).decode('utf-8')
    mock_response.json.return_value = {
        'data': [{'b64_json': fake_b64}]
    }
    mock_client_instance.post.return_value = mock_response

    # Assign the mock client to AsyncClient constructor
    mock_httpx.AsyncClient.return_value = mock_client_instance

    generator = ArtemoxImageGenerator(api_key="test_key")

    prompt = "test prompt"
    input_image_b64 = "input_base64_string"

    result = await generator.generate(prompt=prompt, image=input_image_b64)

    assert result == fake_image_bytes

    # Verify that post was called
    calls = mock_client_instance.post.call_args_list
    assert len(calls) > 0

    # Check payload for 'image' field
    found_image_in_payload = False
    for call in calls:
        args, kwargs = call
        if 'json' in kwargs:
            data = kwargs['json']
            if data.get('image') == input_image_b64:
                found_image_in_payload = True
                break

    assert found_image_in_payload, "Payload should contain 'image' field with input image"

def test_artemox_generate_text_to_image():
    """Тест генерации изображения без исходного изображения (txt2img)"""
    asyncio.run(_test_artemox_generate_text_to_image_async())

async def _test_artemox_generate_text_to_image_async():
    mock_httpx = sys.modules['httpx']
    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.__aexit__.return_value = None

    mock_response = MagicMock()
    mock_response.status_code = 200
    fake_image_bytes = b"fake_image_data_2"
    fake_b64 = base64.b64encode(fake_image_bytes).decode('utf-8')
    mock_response.json.return_value = {
        'data': [{'b64_json': fake_b64}]
    }
    mock_client_instance.post.return_value = mock_response

    mock_httpx.AsyncClient.return_value = mock_client_instance

    generator = ArtemoxImageGenerator(api_key="test_key")

    prompt = "test prompt only"

    result = await generator.generate(prompt=prompt)

    assert result == fake_image_bytes

    # Verify payload does NOT contain 'image'
    calls = mock_client_instance.post.call_args_list
    assert len(calls) > 0

    for call in calls:
        args, kwargs = call
        if 'json' in kwargs:
            data = kwargs['json']
            assert 'image' not in data, "Payload should NOT contain 'image' field for txt2img"
