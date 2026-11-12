"""Fault injection for the reliability experiment (E4).

Sits BETWEEN the cache and the network in the gateway, so cached answers never hide injected faults.
Configure with the WP_CHAOS env var, e.g. WP_CHAOS='{"p_429":0.3,"p_timeout":0.1,"p_malformed":0.1}',
or programmatically with set_chaos({...}) / set_chaos(None).
"""

from __future__ import annotations

import json
import os
import random
import time

_override: dict | None = None
_rng = random.Random(int(os.environ.get("WP_CHAOS_SEED", "1234")))


class InjectedFault(Exception):
    """Looks like a real NIM failure: message starts with the HTTP status so retry logic treats it the same."""


def set_chaos(cfg: dict | None, seed: int | None = None) -> None:
    global _override
    _override = cfg
    if seed is not None:
        _rng.seed(seed)


def current() -> dict:
    if _override is not None:
        return _override
    raw = os.environ.get("WP_CHAOS")
    return json.loads(raw) if raw else {}


def inject(kind: str) -> str | None:
    """Maybe raise a fault (429 / 503 / timeout) or return 'malformed' to corrupt the response. None = healthy."""
    cfg = current()
    if not cfg:
        return None
    kinds = cfg.get("kinds")  # optionally restrict to e.g. ["chat"]
    if kinds and kind not in kinds:
        return None
    if cfg.get("latency_s"):
        time.sleep(cfg["latency_s"])
    r = _rng.random()
    acc = 0.0
    for key, exc in (("p_429", "[429] Too Many Requests (injected)"), ("p_503", "[503] Service Unavailable (injected)"),
                     ("p_timeout", "Read timed out (injected)")):
        acc += cfg.get(key, 0.0)
        if r < acc:
            raise InjectedFault(exc)
    if r < acc + cfg.get("p_malformed", 0.0):
        return "malformed"
    return None
