from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

NOT_SPECIFIED = "not specified"
LLM_PROVIDER_ENV = "AUTORESEARCHER_LLM_PROVIDER"
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_MODEL_ENV = "DEEPSEEK_MODEL"
DEEPSEEK_BASE_URL_ENV = "DEEPSEEK_BASE_URL"
DEEPSEEK_REASONING_EFFORT_ENV = "DEEPSEEK_REASONING_EFFORT"
DEEPSEEK_THINKING_ENV = "DEEPSEEK_THINKING"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class LLMClient(Protocol):
    """Minimal LLM interface used by evidence-based analyzers."""

    def generate(self, prompt: str) -> str:
        """Return a JSON string produced by the model."""


class LLMClientError(RuntimeError):
    """Raised when an LLM request fails."""


class LLMConfigurationError(LLMClientError):
    """Raised when a real LLM client is missing required configuration."""


class MockLLMClient:
    """Deterministic test client that never calls external APIs."""

    def __init__(self, response: str | dict[str, Any] | None = None) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, str):
            return self.response
        if isinstance(self.response, dict):
            return json.dumps(self.response)
        return json.dumps(_build_default_mock_response(prompt))


class OpenAICompatibleLLMClient:
    """Small stdlib client for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("api_key is required.")
        if not model:
            raise LLMConfigurationError("model is required.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.extra_payload = extra_payload or {}

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLMClient":
        api_key = _get_env("OPENAI_API_KEY")
        model = _get_env("AUTORESEARCHER_LLM_MODEL")
        base_url = _get_env("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            raise LLMConfigurationError("Set OPENAI_API_KEY before using the LLM client.")
        if not model:
            raise LLMConfigurationError("Set AUTORESEARCHER_LLM_MODEL before using the LLM client.")
        return cls(api_key=api_key, model=model, base_url=base_url)

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You produce evidence-based paper analysis JSON. "
                        f"If evidence is missing, write exactly {NOT_SPECIFIED!r}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        payload.update(self.extra_payload)
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AutoResearcher/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMClientError(f"LLM request failed: {exc.code} {details}") from exc
        except urllib.error.URLError as exc:
            raise LLMClientError(f"LLM request failed: {exc.reason}") from exc
        return body["choices"][0]["message"]["content"]


class DeepSeekLLMClient(OpenAICompatibleLLMClient):
    """DeepSeek V4-Pro client using the OpenAI-compatible chat API."""

    @classmethod
    def from_env(cls) -> "DeepSeekLLMClient":
        api_key = _get_env(DEEPSEEK_API_KEY_ENV)
        model = _get_env(DEEPSEEK_MODEL_ENV, DEFAULT_DEEPSEEK_MODEL)
        base_url = _get_env(DEEPSEEK_BASE_URL_ENV, DEFAULT_DEEPSEEK_BASE_URL)
        if not api_key:
            raise LLMConfigurationError("Set DEEPSEEK_API_KEY before using DeepSeek.")
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            extra_payload=_deepseek_extra_payload(),
        )


def build_default_llm_client(mock: bool = False) -> LLMClient:
    """Return a real client when configured, otherwise a deterministic mock."""
    if mock:
        return MockLLMClient()
    provider = _get_env(LLM_PROVIDER_ENV).strip().casefold()
    if provider == "mock":
        return MockLLMClient()
    if provider == "deepseek":
        return DeepSeekLLMClient.from_env()
    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleLLMClient.from_env()
    if _get_env(DEEPSEEK_API_KEY_ENV):
        return DeepSeekLLMClient.from_env()
    if _get_env("OPENAI_API_KEY") and _get_env("AUTORESEARCHER_LLM_MODEL"):
        return OpenAICompatibleLLMClient.from_env()
    return MockLLMClient()


def _deepseek_extra_payload() -> dict[str, Any]:
    thinking = _get_env(DEEPSEEK_THINKING_ENV, "enabled").strip().casefold()
    reasoning_effort = _get_env(DEEPSEEK_REASONING_EFFORT_ENV, "high").strip()
    payload: dict[str, Any] = {}
    if thinking in {"enabled", "disabled"}:
        payload["thinking"] = {"type": thinking}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    return payload


def _get_env(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    return _load_local_env().get(name, default)


def _load_local_env() -> dict[str, str]:
    path = os.getcwd()
    env_path = os.path.join(path, ".env")
    if not os.path.exists(env_path):
        return {}
    values: dict[str, str] = {}
    with open(env_path, encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = _strip_env_quotes(value.strip())
    return values


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _build_default_mock_response(prompt: str) -> dict[str, Any]:
    title = _extract_prompt_block(prompt, "Title") or NOT_SPECIFIED
    abstract = _extract_prompt_block(prompt, "Abstract")
    first_sentence = _first_sentence(abstract)
    problem = _claim_with_evidence(
        first_sentence,
        "abstract",
        "The mock analyzer only uses the supplied abstract as evidence.",
    )
    missing = [
        "motivation",
        "method",
        "datasets",
        "metrics",
        "baselines",
        "main_results",
        "limitations",
        "reproduction_notes",
        "possible_extensions",
    ]
    return {
        "title": title,
        "problem": problem,
        "motivation": _missing_claim(),
        "method": _missing_claim(),
        "datasets": _missing_claim(),
        "metrics": _missing_claim(),
        "baselines": _missing_claim(),
        "main_results": _missing_claim(),
        "limitations": _missing_claim(),
        "reproduction_notes": _missing_claim(),
        "possible_extensions": _missing_claim(),
        "confidence": {
            "level": "low",
            "score": 0.2 if first_sentence else 0.05,
            "missing_information": missing,
            "rationale": "Mock analysis uses only directly visible prompt text.",
        },
    }


def _missing_claim() -> dict[str, Any]:
    return {"claim": NOT_SPECIFIED, "evidence": []}


def _claim_with_evidence(claim: str, source_section: str, reason: str) -> dict[str, Any]:
    if not claim:
        return _missing_claim()
    return {
        "claim": claim,
        "evidence": [
            {
                "source_section": source_section,
                "text": claim,
                "reason": reason,
            }
        ],
    }


def _extract_prompt_block(prompt: str, label: str) -> str:
    pattern = rf"{re.escape(label)}:\n(.*?)(?:\n\n[A-Z][A-Za-z ]+:\n|\Z)"
    match = re.search(pattern, prompt, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned or cleaned == NOT_SPECIFIED:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    return match.group(1).strip() if match else cleaned[:240].strip()
