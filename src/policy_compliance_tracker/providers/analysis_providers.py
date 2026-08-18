"""Provider adapters for optional model-assisted compliance analysis.

The application keeps the deterministic rule-based path separate from model
providers. Cloud providers are called only when the user explicitly selects
one and supplies its API key through the environment.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional fallback for minimal installs
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


load_dotenv()


PROVIDER_LABELS = {
    "rule_based": "Rule-Based Analysis",
    "ollama": "Ollama Local LLM",
    "gemini": "Google Gemini API",
}

DEFAULT_MODELS = {
    "ollama": "qwen2.5:1.5b",
    "gemini": "gemini-3.6-flash",
}

API_KEY_ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
}


class ProviderError(RuntimeError):
    """A safe, user-facing provider configuration or request error."""


@dataclass
class ProviderResponse:
    content: str
    provider: str
    model: str


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider.replace("_", " ").title())


def provider_model(provider: str) -> str:
    env_name = f"{provider.upper()}_MODEL"
    return os.getenv(env_name, DEFAULT_MODELS.get(provider, "")).strip()


def provider_is_configured(provider: str) -> bool:
    if provider in {"rule_based", "ollama"}:
        return True
    return bool(os.getenv(API_KEY_ENV_VARS.get(provider, ""), "").strip())


def provider_configuration_message(provider: str) -> str:
    if provider in {"rule_based", "ollama"}:
        return f"{provider_label(provider)} is selected."
    key_name = API_KEY_ENV_VARS.get(provider)
    if provider_is_configured(provider):
        return f"{provider_label(provider)} is configured with model {provider_model(provider)}."
    return f"Set {key_name} in .env before selecting {provider_label(provider)}."


def _safe_error(body: str, provider: str) -> str:
    message = body[:500].replace("\n", " ").strip()
    key_name = API_KEY_ENV_VARS.get(provider)
    secret = os.getenv(key_name, "") if key_name else ""
    if secret:
        message = message.replace(secret, "[redacted]")
    return message or "The provider returned an empty error response."


def _post_json(provider: str, url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(
            f"{provider_label(provider)} request failed with HTTP {exc.code}: "
            f"{_safe_error(body, provider)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(
            f"{provider_label(provider)} could not be reached: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{provider_label(provider)} returned invalid JSON.") from exc


def _gemini_text(data: Dict[str, Any]) -> str:
    parts = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if part.get("text"):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def _require_api_key(provider: str) -> str:
    key_name = API_KEY_ENV_VARS[provider]
    value = os.getenv(key_name, "").strip()
    if not value:
        raise ProviderError(f"{key_name} is not configured for {provider_label(provider)}.")
    return value


def invoke_provider(provider: str, prompt: str) -> ProviderResponse:
    provider = (provider or "rule_based").strip().lower()
    if provider == "rule_based":
        raise ProviderError("Rule-based analysis does not use a model provider.")

    model = provider_model(provider)
    if not model:
        raise ProviderError(f"No model is configured for {provider_label(provider)}.")

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama

            response = ChatOllama(model=model, temperature=0).invoke(prompt)
        except Exception as exc:
            raise ProviderError(
                f"Ollama could not complete the request: {str(exc)[:400]}"
            ) from exc
        content = getattr(response, "content", "")
        return ProviderResponse(str(content).strip(), provider, model)

    if provider == "gemini":
        api_key = _require_api_key(provider)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model, safe='')}:generateContent"
        )
        data = _post_json(
            provider,
            url,
            {"x-goog-api-key": api_key},
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0},
            },
        )
        content = _gemini_text(data)
    else:
        raise ProviderError(f"Unsupported analysis provider: {provider}")

    if not content:
        raise ProviderError(f"{provider_label(provider)} returned no text.")
    return ProviderResponse(content, provider, model)
