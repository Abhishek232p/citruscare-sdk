from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from citruscare import ConfigurationError, ConsentLedger, Settings


class ConfigurationTests(unittest.TestCase):
    def test_reads_settings_from_environment(self) -> None:
        env = {
            "CITRUSCARE_API_KEY": "test-key",
            "CITRUSCARE_MODEL": "example-model",
            "CITRUSCARE_REQUEST_TIMEOUT": "12.5",
            "CITRUSCARE_MAX_TURNS": "4",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.model, "example-model")
        self.assertEqual(settings.request_timeout, 12.5)
        self.assertEqual(settings.max_turns, 4)

    def test_invalid_numeric_environment_value_is_explicit(self) -> None:
        with patch.dict(os.environ, {"CITRUSCARE_MAX_TURNS": "many"}, clear=True):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()

    def test_rejects_non_https_or_http_base_url(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings(base_url="file:///tmp/provider")

    def test_empty_model_is_not_reported_as_a_numeric_parse_error(self) -> None:
        with patch.dict(os.environ, {"CITRUSCARE_MODEL": ""}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "model must not be empty"):
                Settings.from_env()

    def test_invalid_model_discovery_ttl_is_a_configuration_error(self) -> None:
        with patch.dict(
            os.environ,
            {"CITRUSCARE_MODEL_DISCOVERY_TTL_SECONDS": "not-a-number"},
            clear=True,
        ):
            with self.assertRaises(ConfigurationError):
                Settings.from_env()


class ConsentTests(unittest.TestCase):
    def test_grant_revoke_and_regrant(self) -> None:
        ledger = ConsentLedger()
        grant = ledger.grant("patient-1", "care-coordination")
        self.assertTrue(grant.active)
        self.assertTrue(ledger.has_consent("patient-1", "care-coordination"))
        revoked = ledger.revoke("patient-1", "care-coordination")
        self.assertIsNotNone(revoked.revoked_at)
        self.assertFalse(ledger.has_consent("patient-1", "care-coordination"))
        ledger.grant("patient-1", "care-coordination")
        self.assertTrue(ledger.has_consent("patient-1", "care-coordination"))

    def test_rejects_revoking_missing_consent(self) -> None:
        with self.assertRaises(ValueError):
            ConsentLedger().revoke("patient-1", "care-coordination")


if __name__ == "__main__":
    unittest.main()
