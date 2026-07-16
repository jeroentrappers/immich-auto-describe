"""Route each describe request across the provider fleet.

- Per-provider concurrency cap (semaphore).
- Prefer the least-busy healthy provider.
- On failure, retry on another provider; trip a provider after repeated failures
  and re-probe after a cooldown (self-healing) so a dead backend is skipped, not
  hammered, and rejoins automatically.
"""
import threading
import time

from PIL import Image

from .vlm import Provider


class _Backend:
    def __init__(self, provider: Provider):
        self.p = provider
        self.sem = threading.Semaphore(provider.concurrency)
        self.inflight = 0
        self.fails = 0
        self.down_until = 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        return time.time() >= self.down_until

    def mark_ok(self):
        with self._lock:
            self.fails = 0
            self.down_until = 0.0

    def mark_fail(self):
        with self._lock:
            self.fails += 1
            if self.fails >= 3:                      # trip after 3 consecutive failures
                self.down_until = time.time() + 120  # cooldown, then re-probe
                self.fails = 0


class Fleet:
    def __init__(self, specs: list[dict]):
        self.backends = [_Backend(Provider(s)) for s in specs]

    def _pick(self):
        candidates = [b for b in self.backends if b.available()]
        if not candidates:
            candidates = self.backends  # all tripped -> try anyway (re-probe)
        return sorted(candidates, key=lambda b: b.inflight)

    def analyze(self, image: Image.Image, prompt: str) -> dict:
        last_err = None
        for b in self._pick():
            with b.sem:
                with b._lock:
                    b.inflight += 1
                try:
                    res = b.p.analyze(image, prompt)
                    b.mark_ok()
                    return res
                except Exception as e:
                    last_err = e
                    b.mark_fail()
                finally:
                    with b._lock:
                        b.inflight -= 1
        raise RuntimeError(f"all providers failed; last error: {last_err}")

    def health(self) -> dict:
        return {b.p.name: {"available": b.available(), "inflight": b.inflight,
                           "healthy": b.p.healthy()} for b in self.backends}
