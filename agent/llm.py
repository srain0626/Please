from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class LLMProvider(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    COPILOT = "copilot"
    GEMINI = "gemini"


class GeminiAuthMode(str, Enum):
    AUTO = "auto"
    API_KEY = "api_key"
    CLI = "cli"


@dataclass
class LLMConfig:
    provider: LLMProvider
    model: str
    api_key: str = ""
    dry_run: bool = True
    timeout_s: int = 30
    gemini_auth_mode: GeminiAuthMode = GeminiAuthMode.AUTO


class LLMClient(Protocol):
    provider: LLMProvider

    def complete(self, prompt: str) -> str: ...


class StubLLM:
    def __init__(self, provider: LLMProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    def complete(self, prompt: str) -> str:
        return f"[{self.provider.value}:{self.model}:stub] {prompt}"


class GeminiCLILLM:
    def __init__(self, model: str, timeout_s: int = 60) -> None:
        self.provider = LLMProvider.GEMINI
        self._model = model
        self._timeout_s = timeout_s
        self._gemini_bin = shutil.which("gemini")
        if not self._gemini_bin:
            raise RuntimeError("gemini CLI not found in PATH")

    def complete(self, prompt: str) -> str:
        cmd = [self._gemini_bin, "-m", self._model, "-p", prompt, "--output-format", "json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout_s, check=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"gemini CLI error: {stderr or exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("gemini CLI timed out") from exc

        stdout = (proc.stdout or "").strip()
        if not stdout:
            return ""

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout

        if isinstance(payload, dict):
            if isinstance(payload.get("text"), str):
                return payload["text"]
            candidate = payload.get("candidates")
            if isinstance(candidate, list) and candidate:
                first = candidate[0]
                if isinstance(first, dict):
                    content = first.get("content")
                    if isinstance(content, str):
                        return content
            result = payload.get("result")
            if isinstance(result, str):
                return result
        return stdout


class HTTPChatLLM:
    def __init__(self, config: LLMConfig) -> None:
        self.provider = config.provider
        self._model = config.model
        self._api_key = config.api_key
        self._timeout_s = config.timeout_s

    def complete(self, prompt: str) -> str:
        if self.provider == LLMProvider.OPENAI:
            return self._openai_chat(prompt)
        if self.provider == LLMProvider.CLAUDE:
            return self._claude_messages(prompt)
        if self.provider == LLMProvider.COPILOT:
            return self._copilot_chat(prompt)
        if self.provider == LLMProvider.GEMINI:
            return self._gemini_generate_content(prompt)
        raise ValueError(f"unsupported provider: {self.provider}")

    def _post_json(self, url: str, payload: dict, headers: dict[str, str]) -> dict:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self._timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as err:
            body = err.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{self.provider.value} API error {err.code}: {body}") from err

    def _openai_chat(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        data = self._post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        return data["choices"][0]["message"]["content"]

    def _claude_messages(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = self._post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        return data["content"][0]["text"]

    def _copilot_chat(self, prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        data = self._post_json(
            "https://models.inference.ai.azure.com/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        return data["choices"][0]["message"]["content"]

    def _gemini_generate_content(self, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        data = self._post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            payload,
            headers={"x-goog-api-key": self._api_key},
        )
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        first = candidates[0]
        content = first.get("content", {})
        parts = content.get("parts", [])
        texts = [str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("text")]
        return "\n".join(texts)


def resolve_provider(provider: str) -> LLMProvider:
    try:
        return LLMProvider(provider.lower())
    except ValueError as exc:
        raise ValueError("provider must be one of: openai, claude, copilot, gemini") from exc


def default_model(provider: LLMProvider) -> str:
    if provider == LLMProvider.OPENAI:
        return "gpt-4o-mini"
    if provider == LLMProvider.CLAUDE:
        return "claude-3-5-sonnet-latest"
    if provider == LLMProvider.GEMINI:
        return "gemini-2.5-flash"
    return "gpt-4o-mini"


def load_api_key(provider: LLMProvider) -> str:
    if provider == LLMProvider.OPENAI:
        return os.getenv("OPENAI_API_KEY", "")
    if provider == LLMProvider.CLAUDE:
        return os.getenv("ANTHROPIC_API_KEY", "")
    if provider == LLMProvider.GEMINI:
        return os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    return os.getenv("GITHUB_TOKEN", "")


def _gemini_cli_available() -> bool:
    return shutil.which("gemini") is not None


def create_llm_client(
    provider: LLMProvider,
    model: str | None = None,
    live_api: bool = False,
    gemini_auth_mode: GeminiAuthMode | str = GeminiAuthMode.AUTO,
) -> LLMClient:
    selected_model = model or default_model(provider)
    selected_auth_mode = (
        gemini_auth_mode if isinstance(gemini_auth_mode, GeminiAuthMode) else GeminiAuthMode(gemini_auth_mode)
    )
    api_key = load_api_key(provider)

    if provider == LLMProvider.GEMINI and live_api:
        if selected_auth_mode == GeminiAuthMode.API_KEY:
            if not api_key:
                raise RuntimeError("Gemini API key auth selected but GOOGLE_API_KEY/GEMINI_API_KEY is not set")
            config = LLMConfig(
                provider=provider,
                model=selected_model,
                api_key=api_key,
                dry_run=False,
                gemini_auth_mode=selected_auth_mode,
            )
            return HTTPChatLLM(config)
        if selected_auth_mode == GeminiAuthMode.CLI:
            if not _gemini_cli_available():
                raise RuntimeError("Gemini CLI auth selected but `gemini` executable is not available")
            return GeminiCLILLM(model=selected_model)
        if api_key:
            config = LLMConfig(
                provider=provider,
                model=selected_model,
                api_key=api_key,
                dry_run=False,
                gemini_auth_mode=GeminiAuthMode.API_KEY,
            )
            return HTTPChatLLM(config)
        if _gemini_cli_available():
            return GeminiCLILLM(model=selected_model)

    dry_run = not live_api or not api_key
    if dry_run:
        return StubLLM(provider=provider, model=selected_model)

    config = LLMConfig(provider=provider, model=selected_model, api_key=api_key, dry_run=False)
    return HTTPChatLLM(config)
