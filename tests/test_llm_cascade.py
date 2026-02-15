import sys
import unittest
from unittest.mock import MagicMock, patch

# Create mocks for dependencies that might be missing or problematic
mock_config = MagicMock()
mock_config.GEMINI_API_BASE = "http://mock.api"
mock_config.GEMINI_API_KEY = "mock_key"
mock_config.PREFERRED_MODELS = ["model1", "model2"]

# Explicitly set these to integers to avoid MagicMock comparison errors
mock_config.MODEL_TIMEOUT_SEC = 10
mock_config.CIRCUIT_FAILURE_THRESHOLD = 3
mock_config.CIRCUIT_COOLDOWN_SEC = 60

mock_config.settings = MagicMock()
mock_config.settings.DEEPSEEK_API_KEY = ""
mock_config.settings.OPENAI_API_KEY = ""
sys.modules['config'] = mock_config

sys.modules['httpx'] = MagicMock()
sys.modules['utils'] = MagicMock()
sys.modules['utils.metrics'] = MagicMock()
sys.modules['database'] = MagicMock()

# Now import the module under test
if 'services.llm_cascade' in sys.modules:
    del sys.modules['services.llm_cascade']

from services import llm_cascade  # noqa: E402

class TestLLMCascadeLogic(unittest.IsolatedAsyncioTestCase):
    async def test_model_reordering_logic(self):
        # Setup providers
        provider = llm_cascade.LLMProvider(
            name="artemox",
            api_base="base",
            api_key="key",
            models=["model1", "model2", "model3"]
        )

        # Patch _get_providers to return our provider
        with patch('services.llm_cascade._get_providers', return_value=[provider]):
            # Patch _chat_completion_request to track calls and return a dummy response
            # We need to return (text, tokens, error)

            async def mock_request_side_effect(prov, model, *args, **kwargs):
                return "response", 10, None

            with patch('services.llm_cascade._chat_completion_request', side_effect=mock_request_side_effect) as mock_req:

                # Case 1: hint is "model2" (in list)
                print("Running Case 1: Hint in list")
                await llm_cascade.chat_completion([], model_hint="model2")

                # Check first call model
                args, _ = mock_req.call_args_list[0]
                _, called_model = args[0], args[1]
                print(f"Case 1 result: First call to {called_model}")
                # Should be model2 because it was prioritized
                self.assertEqual(called_model, "model2")

                mock_req.reset_mock()

                # Case 2: hint is "modelX" (not in list)
                print("Running Case 2: Hint not in list")
                await llm_cascade.chat_completion([], model_hint="modelX")

                args, _ = mock_req.call_args_list[0]
                _, called_model = args[0], args[1]
                print(f"Case 2 result: First call to {called_model}")
                # Should be modelX
                self.assertEqual(called_model, "modelX")

                mock_req.reset_mock()

                # Case 3: hint is None
                print("Running Case 3: No hint")
                await llm_cascade.chat_completion([], model_hint=None)
                args, _ = mock_req.call_args_list[0]
                _, called_model = args[0], args[1]
                print(f"Case 3 result: First call to {called_model}")
                # Should be model1 (first in list)
                self.assertEqual(called_model, "model1")

if __name__ == '__main__':
    unittest.main()
