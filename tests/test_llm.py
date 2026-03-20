import os
import unittest
from unittest.mock import patch

from agent.llm import GeminiAuthMode, GeminiCLILLM, HTTPChatLLM, LLMProvider, StubLLM, create_llm_client, default_model


class GeminiLLMTests(unittest.TestCase):
    def test_default_model_includes_gemini(self) -> None:
        self.assertEqual(default_model(LLMProvider.GEMINI), 'gemini-2.5-flash')

    def test_gemini_api_key_mode_uses_http_client(self) -> None:
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}, clear=False):
            client = create_llm_client(
                provider=LLMProvider.GEMINI,
                model='gemini-2.5-flash',
                live_api=True,
                gemini_auth_mode=GeminiAuthMode.API_KEY,
            )
        self.assertIsInstance(client, HTTPChatLLM)

    def test_gemini_cli_mode_uses_cli_client(self) -> None:
        with patch('agent.llm.shutil.which', return_value='/usr/bin/gemini'):
            client = create_llm_client(
                provider=LLMProvider.GEMINI,
                model='gemini-2.5-flash',
                live_api=True,
                gemini_auth_mode=GeminiAuthMode.CLI,
            )
        self.assertIsInstance(client, GeminiCLILLM)

    def test_gemini_auto_prefers_api_key_then_cli(self) -> None:
        with patch.dict(os.environ, {'GOOGLE_API_KEY': 'google-key'}, clear=False):
            client = create_llm_client(
                provider=LLMProvider.GEMINI,
                model='gemini-2.5-flash',
                live_api=True,
                gemini_auth_mode=GeminiAuthMode.AUTO,
            )
        self.assertIsInstance(client, HTTPChatLLM)

        with patch.dict(os.environ, {}, clear=True), patch('agent.llm.shutil.which', return_value='/usr/bin/gemini'):
            client = create_llm_client(
                provider=LLMProvider.GEMINI,
                model='gemini-2.5-flash',
                live_api=True,
                gemini_auth_mode=GeminiAuthMode.AUTO,
            )
        self.assertIsInstance(client, GeminiCLILLM)

    def test_gemini_falls_back_to_stub_when_not_live(self) -> None:
        client = create_llm_client(
            provider=LLMProvider.GEMINI,
            model='gemini-2.5-flash',
            live_api=False,
        )
        self.assertIsInstance(client, StubLLM)


if __name__ == '__main__':
    unittest.main()
