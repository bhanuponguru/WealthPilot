"""Probability-of-default model trained on real SBA 7(a) outcomes.

Label: 1 = charged off within 5 years of approval; 0 = anything else (paid in full, or still active =
"EXEMPT"). Every FY2010-2019 approval has >= 6 years of history in the as-of 2026-09-30 file, so there is no
right-censoring. CANCLD / COMMIT (never disbursed) are excluded. Only approved loans appear in the data
(selective labels): see the report's fairness section.

Two leakage traps found while building this (both measured, see plan notes):
 * `TermInMonths` holds the REALISED term for charged-off loans (e.g. 7, 43, 52 months) but the original
   round term for paid loans, so it alone gives AUC 0.95. It is NOT a feature.
 * Filtering on that field also biases the sample, so we do not filter on it.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
import polars as pl

from ..config import ARTIFACTS_DIR, DATA_DIR

SBA_CSV = DATA_DIR / "sba" / "raw" / "FOIA_7a_FY2010_FY2019_asof_260930.csv"
MODEL_PATH = ARTIFACTS_DIR / "pd_model.joblib"
METRICS_PATH = ARTIFACTS_DIR / "pd_metrics.json"

CAT = ["naics2", "business_age", "business_type", "state", "fixed_var", "collateral"]
NUM = ["log_loan", "jobs", "franchise"]
FEATURES = NUM + CAT

REASON_TEXT = {
    "log_loan": "Requested loan amount", "term_months": "Loan term", "jobs": "Jobs supported by the business",
    "franchise": "Franchise status", "naics2": "Industry sector", "business_age": "Age of business",
    "business_type": "Legal form of business", "state": "Borrower state", "fixed_var": "Interest rate type",
    "collateral": "Collateral pledged",
}
# fixed: SBA 'BusinessAge' categories
def business_age_category(years: float) -> str:
    if years < 1:
        return "New, Less than 1 Year old"
    if years < 2:
        return "New, Less than 1 Year old"
    if years < 3:
        return "Less than 3 years old but at least 2"
    if years < 4:
        return "Less than 4 years old but at least 3"
    if years < 5:
        return "Less than 5 years old but at least 4"
    return "Existing, 5 or more years"


REGION = {  # Census regions (proxy group for the fairness audit)
    **{s: "Northeast" for s in "CT ME MA NH RI VT NJ NY PA".split()},
    **{s: "Midwest" for s in "IL IN MI OH WI IA KS MN MO NE ND SD".split()},
    **{s: "South" for s in "DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX".split()},
    **{s: "West" for s in "AZ CO ID MT NV NM UT WY AK CA HI OR WA".split()},
}


HORIZON_DAYS = int(5 * 365.25)


def load_labelled() -> pd.DataFrame:
    cols = ["ApprovalFY", "ApprovalDate", "ChargeOffDate", "LoanStatus", "GrossApproval", "NaicsCode", "BusinessAge", "BusinessType",
            "BorrState", "FixedorVariableInterestInd", "CollateralInd", "JobsSupported", "FranchiseCode"]
    df = pl.read_csv(SBA_CSV, columns=cols, infer_schema_length=50000, ignore_errors=True)
    df = df.filter(~pl.col("LoanStatus").is_in(["CANCLD", "COMMIT"]) & pl.col("GrossApproval").is_not_null())
    days_to_co = (pl.col("ChargeOffDate").str.to_date("%Y-%m-%d", strict=False) - pl.col("ApprovalDate").str.to_date("%Y-%m-%d", strict=False)).dt.total_days()
    df = df.with_columns(
        ((pl.col("LoanStatus") == "CHGOFF") & (days_to_co <= HORIZON_DAYS)).cast(pl.Int8).alias("label"),
        pl.col("GrossApproval").clip(1000, None).log1p().alias("log_loan"),
        pl.col("JobsSupported").fill_null(0).clip(0, 200).alias("jobs"),
        pl.col("FranchiseCode").is_not_null().cast(pl.Int8).alias("franchise"),
        (pl.col("NaicsCode").fill_null(0) // 10000).cast(pl.Utf8).alias("naics2"),
        pl.col("BusinessAge").fill_null("Unanswered").alias("business_age"),
        pl.col("BusinessType").fill_null("CORPORATION").alias("business_type"),
        pl.col("BorrState").fill_null("NA").alias("state"),
        pl.col("FixedorVariableInterestInd").fill_null("V").alias("fixed_var"),
        pl.col("CollateralInd").fill_null("N").alias("collateral"),
    )
    df = df.filter(pl.col("label").is_not_null())  # charge-offs with no date: horizon undeterminable, dropped
    out = df.select(["ApprovalFY", "label"] + FEATURES).to_pandas()
    out["region"] = out["state"].map(REGION).fillna("Other")
    return out


def _cat_frame(df: pd.DataFrame, cats: dict[str, list[str]]) -> pd.DataFrame:
    X = df[FEATURES].copy()
    for c in CAT:
        X[c] = pd.Categorical(X[c].astype(str), categories=cats[c])
    return X


def train(log_mlflow: bool = True) -> dict:
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score

    df = load_labelled()
    cats = {c: sorted(df[c].astype(str).unique().tolist()) for c in CAT}
    tr, cal, te = df[df.ApprovalFY <= 2015], df[df.ApprovalFY == 2016], df[df.ApprovalFY >= 2017]
    Xtr, Xcal, Xte = (_cat_frame(d, cats) for d in (tr, cal, te))
    model = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, random_state=0, verbose=-1)
    model.fit(Xtr, tr.label, eval_set=[(Xcal, cal.label)], callbacks=[lgb.early_stopping(40, verbose=False)])
    raw_cal, raw_te = model.predict_proba(Xcal)[:, 1], model.predict_proba(Xte)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999).fit(raw_cal, cal.label)
    p_te = iso.predict(raw_te)
    metrics = {
        "n_train": len(tr), "n_cal": len(cal), "n_test": len(te), "base_rate_train": float(tr.label.mean()), "base_rate_test": float(te.label.mean()),
        "auc_test": float(roc_auc_score(te.label, raw_te)), "brier_test_calibrated": float(brier_score_loss(te.label, p_te)),
        "brier_test_raw": float(brier_score_loss(te.label, raw_te)), "mean_pred_test": float(p_te.mean()),
        "best_iteration": int(model.best_iteration_ or model.n_estimators), "split": "label=chargeoff within 5y; train FY2010-15, calibrate FY2016, test FY2017-19",
    }
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump({"model": model, "iso": iso, "cats": cats, "metrics": metrics, "version": "pd-lgbm-v1"}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    if log_mlflow:
        _log_mlflow(model, metrics, Xtr.head(50))
    return metrics


def _log_mlflow(model, metrics: dict, sample: pd.DataFrame) -> None:
    import mlflow

    from ..config import get_settings
    try:
        mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
        mlflow.set_experiment("wealthpilot-pd-model")
        with mlflow.start_run(run_name="pd-lgbm-v1"):
            mlflow.log_params({"model": "LightGBM", "features": ",".join(FEATURES), "split": metrics["split"]})
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
            mlflow.log_artifact(str(METRICS_PATH))
            mlflow.lightgbm.log_model(model, name="model", registered_model_name="wealthpilot-pd", input_example=sample)
    except Exception as e:  # MLflow being down must not block training
        print("MLflow logging skipped:", type(e).__name__, str(e)[:120])


@lru_cache
def _bundle() -> dict:
    return joblib.load(MODEL_PATH)


@lru_cache
def _explainer():
    import shap
    return shap.TreeExplainer(_bundle()["model"])


def applicant_features(profile: dict, loan_amount: float, term_months: int, years_in_business: float,
                       naics: str, has_collateral: bool) -> pd.DataFrame:
    row = {
        "log_loan": math.log1p(max(loan_amount, 1000)), "jobs": min(max(profile.get("jobs_supported", 0), 0), 200),
        "franchise": int(bool(profile.get("franchise"))), "naics2": str(int(naics) // 10000),
        "business_age": business_age_category(years_in_business), "business_type": profile.get("business_type", "CORPORATION"),
        "state": profile.get("state", "NA"), "fixed_var": profile.get("fixed_or_variable", "V"), "collateral": "Y" if has_collateral else "N",
    }
    return pd.DataFrame([row])


def score(frame: pd.DataFrame, top_k: int = 3) -> dict:
    """Calibrated PD + top risk-increasing SHAP reasons for a 1-row feature frame."""
    b = _bundle()
    X = _cat_frame(frame, b["cats"])
    raw = float(b["model"].predict_proba(X)[:, 1][0])
    pd_cal = float(b["iso"].predict([raw])[0])
    sv = _explainer().shap_values(X)
    sv = sv[1] if isinstance(sv, list) else sv
    contrib = dict(zip(FEATURES, np.asarray(sv).reshape(-1)[: len(FEATURES)]))
    reasons = [{"feature": f, "reason": REASON_TEXT[f], "shap": round(float(v), 4), "value": str(frame.iloc[0][f])}
               for f, v in sorted(contrib.items(), key=lambda kv: -kv[1])[:top_k] if v > 0]
    return {"pd": round(pd_cal, 4), "model_version": b["version"], "reasons": reasons}


if __name__ == "__main__":
    m = train()
    print(json.dumps(m, indent=2))
