"""MLflow tracing for the underwriting graph.

`enable()` turns on LangChain/LangGraph autolog (every node, LLM call and tool call becomes a span) and `case_trace()` wraps
one underwriting run in a parent span tagged with the case id and policy, so each case is ONE trace in the MLflow UI.
Tracing is best-effort: if MLflow is unreachable the run proceeds untraced. Per-call latency, tokens, retries and fallbacks
are additionally stored in the Postgres `nim_calls` table (tagged by case), which the experiments aggregate.
"""

from __future__ import annotations

from contextlib import contextmanager

_enabled = False


def enable() -> bool:
    global _enabled
    if _enabled:
        return True
    try:
        import httpx
        import mlflow

        from .config import get_settings
        uri = get_settings().mlflow_tracking_uri
        if uri.startswith("http"):  # probe first: the client's own connection retries would otherwise stall a run for minutes
            httpx.get(f"{uri}/health", timeout=2).raise_for_status()
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("wealthpilot-traces")
        mlflow.langchain.autolog()
        _enabled = True
    except Exception:  # noqa: BLE001 - observability must never break underwriting
        _enabled = False
    return _enabled


@contextmanager
def case_trace(case_id: str, policy_id: str, thread_id: str, redaction: bool = True):
    """One parent span (= one MLflow trace) per underwriting run, tagged for search."""
    if not _enabled:
        yield None
        return
    try:
        import mlflow
        span_cm = mlflow.start_span(name="underwrite_case")
        span = span_cm.__enter__()
    except Exception:  # noqa: BLE001
        yield None
        return
    try:
        try:
            span.set_inputs({"case_id": case_id, "policy_id": policy_id, "thread_id": thread_id, "redaction": redaction})
            mlflow.update_current_trace(tags={"case_id": case_id, "policy_id": policy_id, "thread_id": thread_id, "redaction": str(redaction)})
        except Exception:  # noqa: BLE001
            pass
        yield span
    finally:
        try:
            span_cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
