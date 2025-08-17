import time
import threading

class TokenBucketLimiter:
    def __init__(self, rate_per_sec: int = 60):
        self.rate = max(1, rate_per_sec)
        self.tokens = self.rate
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self):
        while True:
            with self._lock:
                now = time.monotonic()
                refill = int((now - self.updated) * self.rate)
                if refill > 0:
                    self.tokens = min(self.rate, self.tokens + refill)
                    self.updated = now
                if self.tokens > 0:
                    self.tokens -= 1
                    return
            time.sleep(0.005)