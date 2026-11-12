"""NIM gateway: the ONLY place the project talks to NVIDIA NIM (chat, vision, rerank) and to Ollama (embeddings).

Per call: shared Postgres cache -> [fault injection] -> shared token bucket (RPM budget) -> network, wrapped in
retry-with-backoff, a circuit breaker per model, and a fallback model. Used by the graph, every MCP server
and the experiments, so budget and cache are global.
"""

from __future__ import annotations

import asyncio
import re
import time

import httpx
import pybreaker
from langchain_core.documents import Document
from langchain_core.messages import messages_from_dict, messages_to_dict
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_nvidia_ai_endpoints import ChatNVIDIA, NVIDIARerank
from pydantic import PrivateAttr
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from ..config import get_settings
from . import chaos, store

_STATUS = re.compile(r"\[(\d{3})\]")


def status_of(e: Exception) -> int | None:
    m = _STATUS.search(str(e))
    return int(m.group(1)) if m else None


def is_retryable(e: Exception) -> bool:
    s = status_of(e)
    if s is not None:
        return s == 429 or s >= 500
    txt = str(e).lower()
    return isinstance(e, (httpx.TransportError, TimeoutError, ConnectionError)) or any(w in txt for w in ("timed out", "timeout", "connection"))


def is_gone(e: Exception) -> bool:
    return status_of(e) in (404, 410)  # retired / unknown model: do not retry, switch to fallback


# Optional observer for experiments: called as hook(tag, messages) for every chat request (cache hit or not).
prompt_hook = None

_breakers: dict[str, pybreaker.CircuitBreaker] = {}


def breaker(name: str) -> pybreaker.CircuitBreaker:
    if name not in _breakers:
        # only availability failures open the breaker, not e.g. 400 bad request
        _breakers[name] = pybreaker.CircuitBreaker(fail_max=4, reset_timeout=30, name=name,
                                                   exclude=[lambda e: status_of(e) == 429 or not (is_retryable(e) or is_gone(e))])  # rate limits back off; they are not outages
    return _breakers[name]


def reset_breakers() -> None:
    _breakers.clear()


def call_with_retry(fn, attempts: int = 4):
    """Run fn() with exponential backoff on retryable errors. Returns (result, retries_used)."""
    n = 0
    for attempt in Retrying(stop=stop_after_attempt(attempts), wait=wait_exponential_jitter(initial=2, max=25),
                            retry=retry_if_exception(lambda e: is_retryable(e) and not is_gone(e)), reraise=True):
        with attempt:
            n = attempt.retry_state.attempt_number - 1
            return fn(), n


# ------------------------------------------------------------------ chat / vision
def _result_to_dict(res: ChatResult) -> dict:
    return {"message": messages_to_dict([res.generations[0].message])[0]}


def _dict_to_result(d: dict) -> ChatResult:
    return ChatResult(generations=[ChatGeneration(message=messages_from_dict([d["message"]])[0])])


def _norm_messages(messages) -> list[dict]:
    """Cache-key view of a conversation: only what determines the model's output (role, content, tool calls).
    Ids, usage and response metadata differ run to run and would defeat the cache."""
    out = []
    for m in messages:
        d = {"type": m.type, "content": m.content}
        if getattr(m, "tool_calls", None):
            d["tool_calls"] = [{"name": t["name"], "args": t["args"], "id": t.get("id")} for t in m.tool_calls]
        if getattr(m, "tool_call_id", None):
            d["tool_call_id"] = m.tool_call_id
        out.append(d)
    return out


def _raw_chat(llm: "GatewayChat", messages, stop, run_manager, kwargs) -> ChatResult:
    store.acquire()
    fault = chaos.inject("chat")
    try:
        res = ChatNVIDIA._generate(llm, messages, stop, run_manager, **kwargs)
    except Exception as e:  # noqa: BLE001
        if status_of(e) == 429:
            store.throttle()
        raise
    store.reward()
    first = res.generations[0].message
    if not first.content and not first.tool_calls:  # empty reply (seen from the 550B model): a failure, never cache or accept it
        raise RuntimeError("[502] empty response from model")
    if fault == "malformed":
        msg = res.generations[0].message
        msg.content = "<<corrupted>> {\"unterminated\": "
        msg.tool_calls = []
        msg.additional_kwargs = {}
    return res


def _chat_generate(llm: "GatewayChat", messages, stop, run_manager, kwargs, allow_fallback: bool = True) -> ChatResult:
    kwargs = dict(kwargs)
    kwargs.setdefault("chat_template_kwargs", {"enable_thinking": llm._thinking})
    if prompt_hook is not None and allow_fallback:
        prompt_hook(store._tag.get(), messages)
    key = store.cache_key("chat", llm.model, {"t": llm.temperature, "mt": llm.max_tokens, "stop": stop, "kw": kwargs}, _norm_messages(messages))
    t0 = time.time()
    hit = store.cache_get(key)
    if hit is not None:
        store.log_call("chat", llm.model, True, True, int((time.time() - t0) * 1000))
        return _dict_to_result(hit)
    try:
        # fewer attempts on the fallback path: there is nothing further to fall back to, so fail fast
        res, retries = breaker(llm.model).call(lambda: call_with_retry(lambda: _raw_chat(llm, messages, stop, run_manager, kwargs),
                                                                       attempts=4 if allow_fallback else 2))
    except Exception as e:
        store.log_call("chat", llm.model, False, False, int((time.time() - t0) * 1000), error=f"{type(e).__name__}: {e}")
        if llm._fallback is not None and allow_fallback:
            return _chat_generate(llm._fallback, messages, stop, run_manager, kwargs, allow_fallback=False)
        raise
    usage = getattr(res.generations[0].message, "usage_metadata", None) or {}
    store.log_call("chat", llm.model, False, True, int((time.time() - t0) * 1000), retries,
                   prompt_tokens=usage.get("input_tokens"), completion_tokens=usage.get("output_tokens"))
    if "<<corrupted>>" not in str(res.generations[0].message.content):  # never cache injected garbage
        store.cache_put(key, "chat", llm.model, _result_to_dict(res))
    return res


class GatewayChat(ChatNVIDIA):
    """ChatNVIDIA routed through the gateway. Works with bind_tools / create_agent / structured output."""
    _fallback: "GatewayChat | None" = PrivateAttr(default=None)
    _thinking: bool = PrivateAttr(default=False)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        return _chat_generate(self, messages, stop, run_manager, kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        return await asyncio.to_thread(_chat_generate, self, messages, stop, None, kwargs)


def _make(model: str, thinking: bool, max_tokens: int, temperature: float) -> GatewayChat:
    s = get_settings()
    llm = GatewayChat(model=model, api_key=s.nvidia_api_key.get_secret_value(), temperature=temperature, max_tokens=max_tokens)
    llm._thinking = thinking
    llm._client.timeout = s.nim_timeout_s
    return llm


def get_chat(thinking: bool | None = None, max_tokens: int = 3000, temperature: float = 0.0, fallback: bool = True) -> GatewayChat:
    s = get_settings()
    th = s.nim_thinking if thinking is None else thinking
    llm = _make(s.chat_model, th, max_tokens, temperature)
    if fallback and s.chat_fallback_model:
        llm._fallback = _make(s.chat_fallback_model, th, max_tokens, temperature)
    return llm


def get_vlm(max_tokens: int = 3000) -> GatewayChat:
    return _make(get_settings().vlm_model, False, max_tokens, 0.0)


# ------------------------------------------------------------------ embeddings (local Ollama)
def embed(texts: list[str], kind: str = "document", batch: int = 32) -> list[list[float]]:
    s = get_settings()
    prefix = "search_document: " if kind == "document" else "search_query: "
    keys = [store.cache_key("embed", s.embed_model, {}, prefix + t) for t in texts]
    out: list[list[float] | None] = [None] * len(texts)
    if s.nim_cache_enabled:
        with store.pool().connection() as c:
            rows = c.execute("SELECT key, response FROM nim_cache WHERE key = ANY(%s)", (keys,)).fetchall()
        found = {k: r for k, r in rows}
        for i, k in enumerate(keys):
            if k in found:
                out[i] = found[k]["v"]
    miss = [i for i, v in enumerate(out) if v is None]
    for b in range(0, len(miss), batch):
        idx = miss[b:b + batch]
        t0 = time.time()

        def call():
            r = httpx.post(f"{s.ollama_url}/api/embed", json={"model": s.embed_model, "input": [prefix + texts[i] for i in idx]}, timeout=180)
            r.raise_for_status()
            return r.json()["embeddings"]
        vecs, retries = call_with_retry(call)
        store.log_call("embed", s.embed_model, False, True, int((time.time() - t0) * 1000), retries)
        for i, v in zip(idx, vecs):
            out[i] = v
            store.cache_put(keys[i], "embed", s.embed_model, {"v": v})
    return out  # type: ignore[return-value]


# ------------------------------------------------------------------ rerank (NIM)
def rerank(query: str, docs: list[str]) -> list[float]:
    """Relevance score per doc (aligned to input order). Raises if NIM rerank is unavailable."""
    s = get_settings()
    key = store.cache_key("rerank", s.rerank_model, {}, {"q": query, "d": docs})
    t0 = time.time()
    hit = store.cache_get(key)
    if hit is not None:
        store.log_call("rerank", s.rerank_model, True, True, int((time.time() - t0) * 1000))
        return hit["scores"]

    def call():
        store.acquire()
        chaos.inject("rerank")
        rr = NVIDIARerank(model=s.rerank_model, api_key=s.nvidia_api_key.get_secret_value(), top_n=len(docs))
        ranked = rr.compress_documents([Document(page_content=d, metadata={"i": i}) for i, d in enumerate(docs)], query)
        scores = [float("-inf")] * len(docs)
        for d in ranked:
            scores[d.metadata["i"]] = float(d.metadata["relevance_score"])
        return scores
    try:
        scores, retries = breaker("rerank").call(lambda: call_with_retry(call))
    except Exception as e:
        store.log_call("rerank", s.rerank_model, False, False, int((time.time() - t0) * 1000), error=f"{type(e).__name__}: {e}")
        raise
    store.log_call("rerank", s.rerank_model, False, True, int((time.time() - t0) * 1000), retries)
    store.cache_put(key, "rerank", s.rerank_model, {"scores": scores})
    return scores
