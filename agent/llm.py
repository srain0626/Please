from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class LLMProvider(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    COPILOT = "copilot"


@dataclass
class LLMConfig:
    provider: LLMProvider
    model: str
    api_key: str = ""
    dry_run: bool = True
    timeout_s: int = 30


class LLMClient(Protocol):
    provider: LLMProvider

    def complete(self, prompt: str) -> str: ...


class StubLLM:
    def __init__(self, provider: LLMProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    def complete(self, prompt: str) -> str:
        return f"[{self.provider.value}:{self.model}:stub] {prompt}"


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


def resolve_provider(provider: str) -> LLMProvider:
    try:
        return LLMProvider(provider.lower())
    except ValueError as exc:
        raise ValueError("provider must be one of: openai, claude, copilot") from exc


def default_model(provider: LLMProvider) -> str:
    if provider == LLMProvider.OPENAI:
        return "gpt-4o-mini"
    if provider == LLMProvider.CLAUDE:
        return "claude-3-5-sonnet-latest"
    return "gpt-4o-mini"


def load_api_key(provider: LLMProvider) -> str:
    if provider == LLMProvider.OPENAI:
        return os.getenv("OPENAI_API_KEY", "")
    if provider == LLMProvider.CLAUDE:
        return os.getenv("ANTHROPIC_API_KEY", "")
    return os.getenv("GITHUB_TOKEN", "")


def create_llm_client(provider: LLMProvider, model: str | None = None, live_api: bool = False) -> LLMClient:
    selected_model = model or default_model(provider)
    api_key = load_api_key(provider)
    dry_run = not live_api or not api_key
    if dry_run:
        return StubLLM(provider=provider, model=selected_model)

    config = LLMConfig(provider=provider, model=selected_model, api_key=api_key, dry_run=False)
    return HTTPChatLLM(config)
