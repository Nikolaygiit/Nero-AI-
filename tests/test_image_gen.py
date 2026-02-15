import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Use unittest.mock.patch.dict to mock sys.modules safely
# This avoids polluting global state for other tests


@pytest.fixture
def mock_dependencies():
    """Mocks external dependencies for the duration of the test"""
    with patch.dict(
        "sys.modules",
        {
            "httpx": MagicMock(),
            "sqlalchemy": MagicMock(),
            "sqlalchemy.ext.asyncio": MagicMock(),
            "pydantic": MagicMock(),
            "pydantic_settings": MagicMock(),
            "structlog": MagicMock(),
            "telegram": MagicMock(),
            "telegram.ext": MagicMock(),
            "telegram.error": MagicMock(),
            "config": MagicMock(),
            "database": MagicMock(),
        },
    ):
        # Set up specific mocks
        sys_modules = sys.modules

        # Config
        mock_config = sys_modules["config"]
        mock_config.GEMINI_API_KEY = "test_key"
        mock_config.GEMINI_API_BASE = "http://test.api"
        mock_config.IMAGE_STYLES = {}
        mock_config.IMAGE_SIZES = {}

        # Database
        mock_db = MagicMock()
        mock_db.update_stats = AsyncMock()
        sys_modules["database"].db = mock_db

        yield sys_modules


def test_artemox_generate_with_image(mock_dependencies):
    """Тест генерации изображения с исходным изображением (img2img)"""
    # Import inside the test function/context to ensure it uses mocked modules
    # We need to reload/import here because if it was already imported, it won't pick up mocks
    # But since we use patch.dict context manager, previous imports might persist if not carefully handled.
    # Ideally, we should remove the module from sys.modules first if it exists.

    if "services.image_gen" in sys.modules:
        del sys.modules["services.image_gen"]

    from services.image_gen import ArtemoxImageGenerator

    asyncio.run(_test_artemox_generate_with_image_async(mock_dependencies, ArtemoxImageGenerator))


async def _test_artemox_generate_with_image_async(mock_modules, generator_cls):
    mock_httpx = mock_modules["httpx"]

    # Setup client mock
    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.__aexit__.return_value = None

    # Setup response
    mock_response = MagicMock()
    mock_response.status_code = 200
    fake_image_bytes = b"fake_image_data"
    fake_b64 = base64.b64encode(fake_image_bytes).decode("utf-8")
    mock_response.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_client_instance.post.return_value = mock_response

    mock_httpx.AsyncClient.return_value = mock_client_instance

    generator = generator_cls(api_key="test_key")
    prompt = "test prompt"
    input_image_b64 = "input_base64_string"

    result = await generator.generate(prompt=prompt, image=input_image_b64)

    assert result == fake_image_bytes

    # Verify call
    calls = mock_client_instance.post.call_args_list
    assert len(calls) > 0
    found = False
    for call in calls:
        args, kwargs = call
        if "json" in kwargs and kwargs["json"].get("image") == input_image_b64:
            found = True
            break
    assert found


def test_artemox_generate_text_to_image(mock_dependencies):
    """Тест генерации изображения без исходного изображения (txt2img)"""
    if "services.image_gen" in sys.modules:
        del sys.modules["services.image_gen"]

    from services.image_gen import ArtemoxImageGenerator

    asyncio.run(_test_artemox_generate_text_to_image_async(mock_dependencies, ArtemoxImageGenerator))


async def _test_artemox_generate_text_to_image_async(mock_modules, generator_cls):
    mock_httpx = mock_modules["httpx"]
    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.__aexit__.return_value = None

    mock_response = MagicMock()
    mock_response.status_code = 200
    fake_image_bytes = b"fake_image_data_2"
    fake_b64 = base64.b64encode(fake_image_bytes).decode("utf-8")
    mock_response.json.return_value = {"data": [{"b64_json": fake_b64}]}
    mock_client_instance.post.return_value = mock_response

    mock_httpx.AsyncClient.return_value = mock_client_instance

    generator = generator_cls(api_key="test_key")
    result = await generator.generate(prompt="test")

    assert result == fake_image_bytes

    # Verify no image in payload
    calls = mock_client_instance.post.call_args_list
    for call in calls:
        args, kwargs = call
        if "json" in kwargs:
            assert "image" not in kwargs["json"]


import sys
