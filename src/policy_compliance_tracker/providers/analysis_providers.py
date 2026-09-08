"""Provider adapters for optional model-assisted compliance analysis.

The application keeps the deterministic rule-based path separate from model
providers. Cloud providers are called only when the user explicitly selects
one and supplies its API key through the environment or Streamlit secrets.
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
    "ollama": "Ollama Local/Cloud API",
    "gemini": "Google Gemini API",
}

DEFAULT_MODELS = {
    "ollama": "qwen2.5:1.5b",
    "gemini": "gemini-3.6-flash",
}

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/api"

API_KEY_ENV_VARS = {
    "ollama": "OLLAMA_API_KEY",
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


def configured_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, "")).strip()
    except Exception:  # Streamlit secrets are unavailable outside a Streamlit app.
        return ""


def provider_model(provider: str) -> str:
    env_name = f"{provider.upper()}_MODEL"
    return configured_value(env_name) or DEFAULT_MODELS.get(provider, "")


def ollama_base_url() -> str:
    return configured_value("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL


def is_remote_ollama() -> bool:
    return not ollama_base_url().lower().startswith("http://localhost")


def provider_is_configured(provider: str) -> bool:
    if provider == "rule_based":
        return True
    if provider == "ollama" and not is_remote_ollama():
        return True
    return bool(configured_value(API_KEY_ENV_VARS.get(provider, "")))


def provider_configuration_message(provider: str) -> str:
    if provider == "rule_based":
        return f"{provider_label(provider)} is selected."
    if provider == "ollama" and not is_remote_ollama():
        return f"{provider_label(provider)} is configured for the local Ollama server."
    key_name = API_KEY_ENV_VARS.get(provider)
    if provider_is_configured(provider):
        return f"{provider_label(provider)} is configured with model {provider_model(provider)}."
    return f"Set {key_name} in .env or Streamlit secrets before selecting {provider_label(provider)}."


def _safe_error(body: str, provider: str) -> str:
    message = body[:500].replace("\n", " ").strip()
    key_name = API_KEY_ENV_VARS.get(provider)
    secret = configured_value(key_name) if key_name else ""
    if secret:
        message = message.replace(secret, "[redacted]")
    return message or "The provider returned an empty error response."


def _post_json(
    provider: str,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    allow_local_http: bool = False,
) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    if not parsed.netloc or (parsed.scheme != "https" and not (allow_local_http and local_http)):
        raise ProviderError("Cloud provider URL must use HTTPS and include a host.")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
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
    value = configured_value(key_name)
    if not value:
        raise ProviderError(f"{key_name} is not configured for {provider_label(provider)}.")
    return value


def _ollama_text(data: Dict[str, Any]) -> str:
    return str(data.get("message", {}).get("content", "") or data.get("response", "")).strip()


def invoke_provider(provider: str, prompt: str) -> ProviderResponse:
    provider = (provider or "rule_based").strip().lower()
    if provider == "rule_based":
        raise ProviderError("Rule-based analysis does not use a model provider.")

    model = provider_model(provider)
    if not model:
        raise ProviderError(f"No model is configured for {provider_label(provider)}.")

    if provider == "ollama":
        base_url = ollama_base_url().rstrip("/")
        api_key = configured_value("OLLAMA_API_KEY")
        if is_remote_ollama() and not api_key:
            raise ProviderError("OLLAMA_API_KEY is required for a remote Ollama API.")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        data = _post_json(
            provider,
            f"{base_url}/chat",
            headers,
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0},
            },
            allow_local_http=True,
        )
        content = _ollama_text(data)

    elif provider == "gemini":
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
