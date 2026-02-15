import os
import sys
import unittest
from unittest.mock import MagicMock, patch


# Helper for SessionState
class SessionStateMock(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value


class TestAdminSecurity(unittest.TestCase):
    def setUp(self):
        # Setup mocks
        self.mock_st = MagicMock()
        self.mock_st.session_state = SessionStateMock()
        self.mock_st.error = MagicMock()
        self.mock_st.stop = MagicMock(side_effect=SystemExit("st.stop() called"))

        # Patch modules
        self.patcher_st = patch.dict(sys.modules, {"streamlit": self.mock_st})
        self.patcher_st.start()

        # Mock other dependencies if they are imported at module level
        self.mock_pandas = MagicMock()
        self.patcher_pd = patch.dict(sys.modules, {"pandas": self.mock_pandas})
        self.patcher_pd.start()

        self.mock_sqlite3 = MagicMock()
        self.patcher_sql = patch.dict(sys.modules, {"sqlite3": self.mock_sqlite3})
        self.patcher_sql.start()

        # Add project root to path
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def tearDown(self):
        self.patcher_st.stop()
        self.patcher_pd.stop()
        self.patcher_sql.stop()
        if "admin.app" in sys.modules:
            del sys.modules["admin.app"]

    def test_admin_access_denied_without_password(self):
        """Verify that access is denied if ADMIN_PANEL_PASSWORD is not set"""
        # Set environment variable to empty string
        with patch.dict(os.environ, {"ADMIN_PANEL_PASSWORD": ""}):
            # Mock config to also return empty string
            mock_settings = MagicMock()
            mock_settings.ADMIN_PANEL_PASSWORD = ""
            with patch.dict(sys.modules, {"config": MagicMock(settings=mock_settings)}):
                # Import admin.app inside the test to ensure it uses the mocked environment
                # We need to force reload or import it fresh
                if "admin.app" in sys.modules:
                    del sys.modules["admin.app"]

                try:
                    from admin import app

                    # Call check_auth
                    # It should raise SystemExit because st.stop() is mocked to raise SystemExit
                    with self.assertRaises(SystemExit):
                        app.check_auth()

                    # Verify st.error was called
                    self.mock_st.error.assert_called()
                    args, _ = self.mock_st.error.call_args
                    self.assertIn(
                        "Ошибка безопасности: Пароль администратора не установлен", args[0]
                    )
                    self.mock_st.stop.assert_called_once()

                except ImportError:
                    self.fail("Could not import admin.app")

    def test_admin_access_allowed_with_password(self):
        """Verify that access is allowed (or at least check proceeds) if password is set"""
        # Set environment variable to a value
        with patch.dict(os.environ, {"ADMIN_PANEL_PASSWORD": "secret_password"}):
            # Mock config
            mock_settings = MagicMock()
            mock_settings.ADMIN_PANEL_PASSWORD = "secret_password"
            with patch.dict(sys.modules, {"config": MagicMock(settings=mock_settings)}):
                if "admin.app" in sys.modules:
                    del sys.modules["admin.app"]

                from admin import app

                # Should not raise SystemExit
                try:
                    result = app.check_auth()
                except SystemExit:
                    self.fail("check_auth() raised SystemExit unexpectedly when password is set")

                # If session state is empty, it returns False (not authenticated yet), but check passed the pwd guard
                self.assertFalse(result)
                self.mock_st.error.assert_not_called()
                self.mock_st.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
