import sys
import unittest
from unittest.mock import MagicMock, patch


class TestAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create mocks for dependencies that are missing in the environment
        cls.mock_config = MagicMock()
        cls.mock_httpx = MagicMock()
        cls.mock_pydantic = MagicMock()
        cls.mock_pydantic_settings = MagicMock()
        cls.mock_telegram = MagicMock()
        cls.mock_telegram_ext = MagicMock()
        cls.mock_telegram_error = MagicMock()

        # Setup settings mock inside config
        cls.mock_settings = MagicMock()
        cls.mock_config.settings = cls.mock_settings

        # Patch sys.modules to redirect imports to our mocks
        cls.module_patcher = patch.dict(
            sys.modules,
            {
                "config": cls.mock_config,
                "httpx": cls.mock_httpx,
                "pydantic": cls.mock_pydantic,
                "pydantic_settings": cls.mock_pydantic_settings,
                "telegram": cls.mock_telegram,
                "telegram.ext": cls.mock_telegram_ext,
                "telegram.error": cls.mock_telegram_error,
            },
        )
        cls.module_patcher.start()

        # Remove utils.analytics from sys.modules to force reload with mocks
        if "utils.analytics" in sys.modules:
            del sys.modules["utils.analytics"]

        # Import the module under test
        import utils.analytics

        cls.analytics = utils.analytics

    @classmethod
    def tearDownClass(cls):
        cls.module_patcher.stop()
        # Clean up imported module
        if "utils.analytics" in sys.modules:
            del sys.modules["utils.analytics"]

    def setUp(self):
        self.mock_httpx.reset_mock()
        self.mock_settings.reset_mock()

    def test_track_no_api_key(self):
        """Test that track does nothing if API key is not set"""
        # Set API key to empty string so 'if not ...' evaluates to True
        self.mock_settings.POSTHOG_API_KEY = ""
        self.analytics.track("test_event", "user123")
        self.mock_httpx.post.assert_not_called()

    def test_track_success(self):
        """Test successful tracking call"""
        self.mock_settings.POSTHOG_API_KEY = "test_key"
        self.mock_settings.POSTHOG_HOST = "https://test.posthog.com"

        properties = {"prop": "value"}
        self.analytics.track("test_event", "user123", properties)

        self.mock_httpx.post.assert_called_once()
        args, kwargs = self.mock_httpx.post.call_args
        self.assertEqual(args[0], "https://test.posthog.com/capture/")
        self.assertEqual(
            kwargs["json"],
            {
                "api_key": "test_key",
                "event": "test_event",
                "distinct_id": "user123",
                "properties": properties,
            },
        )
        # Check timeout is passed
        self.assertIn("timeout", kwargs)
        self.assertEqual(kwargs["timeout"], 2.0)

    def test_track_error_handling(self):
        """Test that exceptions during tracking are suppressed"""
        self.mock_settings.POSTHOG_API_KEY = "test_key"
        self.mock_settings.POSTHOG_HOST = "https://test.posthog.com"

        # Simulate an error
        self.mock_httpx.post.side_effect = Exception("Network error")

        try:
            self.analytics.track("test_event", "user123")
        except Exception as e:
            self.fail(f"track() raised Exception unexpectedly: {e}")

        self.mock_httpx.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
