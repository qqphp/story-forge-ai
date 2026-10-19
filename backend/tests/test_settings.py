import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.core.database import connection, initialize_schema
from backend.modules.contracts import SettingsPayload
from backend.modules.settings.service import load_settings, save_settings, to_public


class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.db"
        self.defaults = SettingsPayload().model_dump()
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        initialize_schema(self.db)

    def db(self):
        return connection(self.path)

    def store(self, payload):
        with self.db() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(id,payload) VALUES(1,?)", (json.dumps(payload),))

    def test_independent_environment_defaults_and_saved_values_take_precedence(self):
        env = {
            "TEXT_API_BASE": "https://text.example/proxy/v2",
            "TEXT_API_KEY": "text-env-test-key",
            "IMAGE_API_BASE": "https://image.example/custom",
            "IMAGE_API_KEY": "image-env-test-key",
        }
        with patch.dict(os.environ, env):
            settings = load_settings(self.db, self.defaults)
            for field in ("text_api_base", "text_api_key", "image_api_base", "image_api_key"):
                self.assertEqual(settings[field], env[field.upper()])
            saved = {
                "text_api_base": "https://saved-text.example/v1",
                "text_api_key": "text-saved-test-key",
                "image_api_base": "https://saved-image.example/images-api",
                "image_api_key": "image-saved-test-key",
            }
            self.store(saved)
            settings = load_settings(self.db, self.defaults)
            for field, value in saved.items():
                self.assertEqual(settings[field], value)
            self.store({"text_api_key": "", "image_api_key": ""})
            settings = load_settings(self.db, self.defaults)
            self.assertEqual(settings["text_api_key"], "")
            self.assertEqual(settings["image_api_key"], "")
            self.assertEqual(settings["text_api_base"], env["TEXT_API_BASE"])

    def test_legacy_environment_variables_are_ignored(self):
        with patch.dict(os.environ, {"MODEL_API_BASE": "https://legacy.example/v1", "MODEL_API_KEY": "legacy-env-test-key"}):
            settings = load_settings(self.db, self.defaults)
        for field in ("text_api_base", "text_api_key", "image_api_base", "image_api_key"):
            self.assertEqual(settings[field], self.defaults[field])

    def test_speech_base_environment_and_saved_region_are_compatible(self):
        with patch.dict(os.environ, {"AZURE_SPEECH_BASE": "https://custom.speech.example"}, clear=True):
            settings = load_settings(self.db, self.defaults)
            self.assertEqual(settings["azure_speech_base"], "https://custom.speech.example")
            self.store({"azure_speech_region": "westus"})
            settings = load_settings(self.db, self.defaults)
            self.assertEqual(settings["azure_speech_base"], "https://westus.tts.speech.microsoft.com")
            self.assertNotIn("azure_speech_region", settings)
            public = to_public(settings)
            save_settings(self.db, settings, SettingsPayload(**public))
        with self.db() as conn:
            saved = json.loads(conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()["payload"])
        self.assertEqual(saved["azure_speech_base"], "https://westus.tts.speech.microsoft.com")
        self.assertNotIn("azure_speech_region", saved)
        self.store({})
        with patch.dict(os.environ, {"AZURE_SPEECH_REGION": "centralus"}, clear=True):
            settings = load_settings(self.db, self.defaults)
        self.assertEqual(settings["azure_speech_base"], "https://centralus.tts.speech.microsoft.com")

    def test_models_start_empty_and_saved_selection_overrides_environment(self):
        settings = load_settings(self.db, self.defaults)
        self.assertEqual(settings["model"], "")
        self.assertEqual(settings["image_model"], "")
        with patch.dict(os.environ, {"MODEL_NAME": "env-text-model", "IMAGE_MODEL_NAME": "env-image-model"}):
            settings = load_settings(self.db, self.defaults)
            self.assertEqual(settings["model"], "env-text-model")
            self.assertEqual(settings["image_model"], "env-image-model")
            self.store({"model": "saved-text-model", "image_model": ""})
            settings = load_settings(self.db, self.defaults)
        self.assertEqual(settings["model"], "saved-text-model")
        self.assertEqual(settings["image_model"], "")

    def test_legacy_database_configuration_is_mapped_and_saved_as_independent_fields(self):
        self.store({"api_base": "https://legacy.example/proxy", "api_key": "legacy-db-test-key"})
        settings = load_settings(self.db, self.defaults)
        for provider in ("text", "image"):
            self.assertEqual(settings[f"{provider}_api_base"], "https://legacy.example/proxy")
            self.assertEqual(settings[f"{provider}_api_key"], "legacy-db-test-key")
        public = to_public(settings)
        self.assertNotIn("api_base", public)
        self.assertNotIn("api_key", public)
        save_settings(self.db, settings, SettingsPayload(**public))
        with self.db() as conn:
            saved = json.loads(conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()["payload"])
        self.assertNotIn("api_base", saved)
        self.assertNotIn("api_key", saved)
        self.assertEqual(saved["text_api_key"], "legacy-db-test-key")
        self.assertEqual(saved["image_api_key"], "legacy-db-test-key")

    def test_legacy_database_values_do_not_replace_independent_fields(self):
        self.store({
            "api_base": "https://legacy.example/v1", "api_key": "legacy-db-test-key",
            "text_api_base": "https://text.example/v2", "image_api_key": "",
        })
        settings = load_settings(self.db, self.defaults)
        self.assertEqual(settings["text_api_base"], "https://text.example/v2")
        self.assertEqual(settings["image_api_base"], "https://legacy.example/v1")
        self.assertEqual(settings["text_api_key"], "legacy-db-test-key")
        self.assertEqual(settings["image_api_key"], "")

    def test_masked_keys_are_preserved_and_can_be_replaced_or_cleared_independently(self):
        self.store({"text_api_key": "text-db-test-key", "image_api_key": "image-db-test-key"})
        settings = load_settings(self.db, self.defaults)
        public = to_public(settings)
        self.assertEqual(public["text_api_key"], "••••••••")
        self.assertEqual(public["image_api_key"], "••••••••")
        saved = save_settings(self.db, settings, SettingsPayload(**public))
        self.assertEqual(saved["text_api_key"], "text-db-test-key")
        self.assertEqual(saved["image_api_key"], "image-db-test-key")
        public["image_api_key"] = "replacement-image-test-key"
        saved = save_settings(self.db, saved, SettingsPayload(**public))
        self.assertEqual(saved["text_api_key"], "text-db-test-key")
        self.assertEqual(saved["image_api_key"], "replacement-image-test-key")
        public["image_api_key"] = ""
        saved = save_settings(self.db, saved, SettingsPayload(**public))
        self.assertEqual(saved["text_api_key"], "text-db-test-key")
        self.assertEqual(saved["image_api_key"], "")
