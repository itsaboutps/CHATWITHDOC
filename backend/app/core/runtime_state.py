from threading import RLock
from typing import Optional, Dict, Any
import time

_lock = RLock()
_gemini_key: Optional[str] = None
_gemini_last_error: Optional[str] = None
_gemini_last_error_time: Optional[float] = None
_gemini_last_success_time: Optional[float] = None


def set_gemini_key(key: str):
    global _gemini_key, _gemini_last_error, _gemini_last_error_time, _gemini_last_success_time
    with _lock:
        _gemini_key = key.strip() or None
        # Reset error state on new key
        _gemini_last_error = None
        _gemini_last_error_time = None
        _gemini_last_success_time = None


def clear_gemini_key():
    global _gemini_key
    with _lock:
        _gemini_key = None


def get_gemini_key(fallback: str = "") -> str:
    with _lock:
        return _gemini_key or fallback


def has_gemini_key() -> bool:
    with _lock:
        return _gemini_key is not None


def set_gemini_failure(reason: str):
    global _gemini_last_error, _gemini_last_error_time
    with _lock:
        _gemini_last_error = reason.strip()[:160]
        _gemini_last_error_time = time.time()


def set_gemini_success():
    global _gemini_last_success_time, _gemini_last_error
    with _lock:
        _gemini_last_success_time = time.time()
        # keep last error for diagnostics but could optionally clear


def gemini_status() -> Dict[str, Any]:
    with _lock:
        return {
            "active": _gemini_key is not None,
            "last_error": _gemini_last_error,
            "last_error_time": _gemini_last_error_time,
            "last_success_time": _gemini_last_success_time,
        }
