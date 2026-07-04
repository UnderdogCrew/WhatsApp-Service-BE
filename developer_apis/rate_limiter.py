import time
from collections import defaultdict
from threading import Lock

from UnderdogCrew.settings import redis_client

TRY_NOW_RATE_LIMIT = 30
TRY_NOW_RATE_WINDOW_SECONDS = 60

_memory_store = defaultdict(list)
_memory_lock = Lock()


def _check_memory_rate_limit(user_id):
    now = time.time()
    key = str(user_id)

    with _memory_lock:
        timestamps = _memory_store[key]
        timestamps[:] = [ts for ts in timestamps if now - ts < TRY_NOW_RATE_WINDOW_SECONDS]

        if len(timestamps) >= TRY_NOW_RATE_LIMIT:
            return False

        timestamps.append(now)
        return True


def check_try_now_rate_limit(user_id):
    key = f'try_now:{user_id}'

    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, TRY_NOW_RATE_WINDOW_SECONDS)
        return count <= TRY_NOW_RATE_LIMIT
    except Exception:
        return _check_memory_rate_limit(user_id)
