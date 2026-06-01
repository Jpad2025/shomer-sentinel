"""Circuit breaker Redis para SSH al firewall Hunter."""
import os


_CB_FAIL_KEY = "hunter:firewall:fail_count"
_CB_STATUS_KEY = "hunter:firewall:unreachable"
_CB_THRESHOLD = 3
_CB_TTL = 300


def _redis_host() -> str:
    return (os.environ.get("SHOMER_REDIS_HOST") or "127.0.0.1").strip()


def _get_redis():
    try:
        import redis as _redis

        r = _redis.Redis(
            host=_redis_host(),
            port=int(os.environ.get("SHOMER_REDIS_PORT", "6379")),
            db=int(os.environ.get("SHOMER_REDIS_DB", "0")),
            socket_connect_timeout=2,
        )
        r.ping()
        return r
    except Exception:
        return None


def _cb_record_success():
    r = _get_redis()
    if r:
        try:
            r.delete(_CB_FAIL_KEY)
            r.delete(_CB_STATUS_KEY)
        except Exception:
            pass


def _cb_record_failure() -> bool:
    r = _get_redis()
    if not r:
        return False
    try:
        count = r.incr(_CB_FAIL_KEY)
        r.expire(_CB_FAIL_KEY, 600)
        if int(count) >= _CB_THRESHOLD:
            r.set(_CB_STATUS_KEY, "1", ex=_CB_TTL)
            return True
    except Exception:
        pass
    return False


def _cb_is_open() -> bool:
    r = _get_redis()
    if not r:
        return False
    try:
        return bool(r.get(_CB_STATUS_KEY))
    except Exception:
        return False
