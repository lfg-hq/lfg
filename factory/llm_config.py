import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "llm_models.json"


def _config_path() -> Path:
    """Return the absolute path to the model config file."""
    return Path(settings.BASE_DIR) / "config" / _CONFIG_FILENAME


@lru_cache(maxsize=1)
def _load_config() -> Dict[str, Any]:
    """Load the shared model config from disk (cached)."""
    path = _config_path()
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        logger.error("Model config file not found at %s", path)
        return {"providers": {}, "default_model": "gpt-5-mini"}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in model config: %s", exc)
        return {"providers": {}, "default_model": "gpt-5-mini"}


def get_llm_model_config() -> Dict[str, Any]:
    """Expose the cached config for templates and other consumers."""
    return _load_config()


def get_provider_model_mapping(provider_name: str) -> Dict[str, str]:
    """Return {model_key: provider_model_name} for a provider."""
    provider = _load_config().get("providers", {}).get(provider_name, {})
    mapping = {}
    for model in provider.get("models", []):
        provider_model = model.get("provider_model") or model.get("key")
        mapping[model["key"]] = provider_model
    return mapping


def get_model_provider_map() -> Dict[str, str]:
    """Return {model_key: provider_name} for all models."""
    provider_map = {}
    config = _load_config()
    for provider_name, provider in config.get("providers", {}).items():
        for model in provider.get("models", []):
            provider_map[model["key"]] = provider_name
    return provider_map


def get_default_model_key(provider_name: Optional[str] = None) -> Optional[str]:
    """Return the default model key, optionally scoped to a provider."""
    config = _load_config()
    if provider_name:
        provider = config.get("providers", {}).get(provider_name, {})
        return provider.get("default_model") or config.get("default_model")
    return config.get("default_model")


def get_model_metadata(model_key: str) -> Optional[Dict[str, Any]]:
    """Return the metadata dict for a specific model key."""
    config = _load_config()
    for provider in config.get("providers", {}).values():
        for model in provider.get("models", []):
            if model.get("key") == model_key:
                return model
    return None


def get_model_label(model_key: str) -> str:
    """Return the display label for a model key."""
    metadata = get_model_metadata(model_key)
    if metadata:
        return metadata.get("label", model_key)
    return model_key


def get_model_choices() -> List[Tuple[str, str]]:
    """Return (model_key, label) tuples for forms/models."""
    config = _load_config()
    choices: List[Tuple[str, str]] = []
    for provider in config.get("providers", {}).values():
        for model in provider.get("models", []):
            label = model.get("label", model.get("key", ""))
            key = model.get("key")
            if key:
                choices.append((key, label))
    return choices


def get_all_model_keys() -> List[str]:
    """Convenience helper returning only the model keys."""
    return [choice[0] for choice in get_model_choices()]
