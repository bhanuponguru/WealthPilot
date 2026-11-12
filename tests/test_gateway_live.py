"""Live smoke tests for the NIM gateway (need NVIDIA key, Postgres and Ollama). Run: uv run pytest -m live"""
import time

import pytest
from langchain_core.tools import tool

from wealthpilot.nim import embed, get_chat, rerank
from wealthpilot.nim import chaos, gateway, store

pytestmark = pytest.mark.live


@tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def test_chat_tools_and_cache():
    llm = get_chat()
    q = "What is 17.5 + 24.25? Use the add tool."
    t0 = time.time(); r1 = llm.bind_tools([add]).invoke(q); d1 = time.time() - t0
    assert r1.tool_calls and r1.tool_calls[0]["name"] == "add"
    t0 = time.time(); r2 = llm.bind_tools([add]).invoke(q); d2 = time.time() - t0
    assert r2.tool_calls == r1.tool_calls
    assert d2 < 0.5, f"cached call should be fast, took {d2:.2f}s (first {d1:.2f}s)"


def test_embed_and_rerank():
    v = embed(["The minimum DSCR is 1.25.", "Office hours are 9 to 5."])
    assert len(v) == 2 and len(v[0]) == 768
    s = rerank("minimum debt service coverage", ["The minimum DSCR is 1.25.", "Office hours are 9 to 5."])
    assert s[0] > s[1]


def test_retry_recovers_from_injected_429():
    chaos.set_chaos({"p_429": 0.6}, seed=3)
    try:
        store.reset_state(clear_cache=False)
        llm = get_chat(fallback=False)
        r = llm.invoke("Reply with the single word: ok (attempt %f)" % time.time())
        assert r.content
    finally:
        chaos.set_chaos(None)


def test_fallback_when_primary_is_gone():
    from wealthpilot.config import get_settings
    llm = get_chat(fallback=False)
    llm._fallback = gateway._make(get_settings().chat_model, False, 200, 0.0)  # fallback is off by default; configure it here
    llm.model = "nvidia/does-not-exist-model"  # 404 -> immediate fallback to the working model
    gateway.reset_breakers()
    r = llm.invoke("Reply with the single word: ok (fb %f)" % time.time())
    assert r.content


def test_adaptive_rate_limiter():
    """429 -> shared rate drops (multiplicative); successes -> creeps back up (additive), never above the budget."""
    from wealthpilot.config import get_settings
    budget = float(get_settings().nim_rpm_budget)
    store.reset_state()
    assert store.current_rpm() == budget
    store.throttle()
    after_one = store.current_rpm()
    assert after_one == pytest.approx(budget * 0.7)
    for _ in range(20):
        store.throttle()
    assert store.current_rpm() == store.MIN_RPM          # floor
    store.reward(step=1.0)
    assert store.current_rpm() == store.MIN_RPM + 1.0
    for _ in range(100):
        store.reward(step=5.0)
    assert store.current_rpm() == budget                 # ceiling
    store.reset_state()
