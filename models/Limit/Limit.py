import time
import asyncio


class Limit(object):
    def __init__(self, calls=5, period=1):
        self.calls = calls
        self.period = period
        self.clock = time.monotonic
        self.last_reset = 0
        self.num_calls = 0

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            if self.num_calls >= self.calls:
                await asyncio.sleep(self.__period_remaining())

            period_remaining = self.__period_remaining()

            if period_remaining <= 0:
                self.num_calls = 0
                self.last_reset = self.clock()

            self.num_calls += 1

            return await func(*args, **kwargs)

        return wrapper

    def __period_remaining(self):
        elapsed = self.clock() - self.last_reset
        return self.period - elapsed
