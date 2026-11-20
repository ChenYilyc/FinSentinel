"""Short-lived, process-local continuation tokens for the single-user workbench."""
from dataclasses import dataclass
from secrets import token_urlsafe
from threading import Lock
from time import monotonic


class CheckpointGone(Exception):
    pass


class CheckpointBusy(Exception):
    pass


class ProviderConfigChanged(Exception):
    pass


@dataclass
class Entry:
    state: object
    expires: float
    busy: bool = False
    result: dict | None = None


class Checkpoints:
    def __init__(self, capacity=64, ttl_seconds=900):
        self.entries = {}
        self.lock = Lock()
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds

    def _prune(self):
        now = monotonic()
        for token, entry in list(self.entries.items()):
            if not entry.busy and entry.expires <= now:
                del self.entries[token]

    def save(self, state):
        with self.lock:
            self._prune()
            if len(self.entries) >= self.capacity:
                idle = next((key for key, entry in self.entries.items() if not entry.busy), None)
                if idle is None:
                    return None
                del self.entries[idle]
            token = token_urlsafe(32)
            self.entries[token] = Entry(state, monotonic() + self.ttl_seconds)
            return token

    def resume(self, token, advance):
        with self.lock:
            self._prune()
            entry = self.entries.get(token)
            if entry is None:
                raise CheckpointGone()
            if entry.busy:
                raise CheckpointBusy()
            if entry.result is not None:
                return entry.result
            entry.busy = True

        try:
            result = advance(entry.state)
        except ProviderConfigChanged:
            # Configuration is checked before the first outbound request.
            with self.lock:
                entry.busy = False
            raise
        except Exception:
            with self.lock:
                del self.entries[token]
            raise

        with self.lock:
            entry.state = None
            entry.result = result
            entry.expires = monotonic() + self.ttl_seconds
            entry.busy = False
        return result
