"""
Simple JSON-backed cache for LLM/embedding calls made during
evaluation. Never re-pays for the same input twice — critical when
API credits are limited. Cache key is a hash of the function name +
input arguments.

Not used by the production pipeline itself (app/tools/, app/ocr/) —
only by the eval harness, so production behavior is unaffected.
"""

import json
import hashlib
from pathlib import Path
from typing import Callable, Any

CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "sample_dataset" / "eval_cache.json"


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def cached_call(cache_key_parts: list, compute_fn: Callable[[], Any]) -> Any:
    """
    Returns the cached result for cache_key_parts if present, otherwise
    calls compute_fn(), caches the result, and returns it.
    cache_key_parts should be JSON-serializable (strings, numbers).
    """
    cache = _load_cache()
    key = hashlib.sha256(json.dumps(cache_key_parts, sort_keys=True).encode()).hexdigest()

    if key in cache:
        return cache[key]["result"], True  # (result, was_cached)

    result = compute_fn()
    cache[key] = {"input": cache_key_parts, "result": result}
    _save_cache(cache)
    return result, False