import time
import random

class RateLimiter:
    def __init__(self, base_delay=2.5):
        self.base_delay = base_delay
        self.last_request_time = 0

    def wait(self):
        # jittered delay (important to avoid pattern detection)
        delay = self.base_delay + random.uniform(0.5, 3.0)

        elapsed = time.time() - self.last_request_time

        if elapsed < delay:
            time.sleep(delay - elapsed)

        self.last_request_time = time.time()

    def increase_delay(self):
        self.base_delay = min(self.base_delay * 1.5, 30)

    def decrease_delay(self):
        self.base_delay = max(self.base_delay * 0.9, 1.5)