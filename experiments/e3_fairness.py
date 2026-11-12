"""E3 (a)(b): fairness audit of the PD model.

(a) Real SBA data. The public file has NO race/gender/ethnicity fields, so we audit PROXY groups (census region, business
    age, legal form). These are NOT legally protected classes; the numbers show how the audit works on real data and where
    disparities in the model sit. Selective-labels caveat: only approved loans are observed.
(b) Planted bias on synthetic data with a known protected attribute: the audit must detect it, and mitigation should shrink it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from fairlearn.metrics import MetricFrame, demographic_parity_difference, equalized_odds_difference, false_positive_rate, selection_rate, true_positive_rate
from fairlearn.postprocessing import ThresholdOptimizer
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import roc_auc_score

from wealthpilot.risk import pd_model

from common import log_mlflow, md_table, save


def proxy_audit() -> dict:
    df = pd_model.load_labelled()
    te = df[df.ApprovalFY >= 2017].reset_index(drop=True)
    b = pd_model._bundle()
    X = pd_model._cat_frame(te, b["cats"])
    scores = b["iso"].predict(b["model"].predict_proba(X)[:, 1])
    thr = float(np.quantile(scores, 0.80))                    # decline the riskiest 20%
    pred = (scores >= thr).astype(int)
    y = te.label.values
    te = te.assign(age_group=np.where(te.business_age.str.contains("Startup|New|Less than"), "young (<5y/startup)", "established (5y+)"))
    out = {"threshold": round(thr, 4), "n": len(te), "auc": round(float(roc_auc_score(y, scores)), 4), "groups": {}}
    for gname in ("region", "age_group", "business_type"):
        s = te[gname].astype(str)
        mf = MetricFrame(metrics={"selection_rate": selection_rate, "fpr": false_positive_rate, "tpr": true_positive_rate, "base_rate": lambda yt, yp: float(np.mean(yt))},
                         y_true=y, y_pred=pred, sensitive_features=s)
        sizes = s.value_counts()
        keep = sizes[sizes >= 500].index                       # ignore tiny groups
        m = mf.by_group.loc[mf.by_group.index.isin(keep)].round(4)
        mask = s.isin(keep)
        out["groups"][gname] = {
            "by_group": m.assign(n=sizes.loc[m.index]).to_dict("index"),
            "demographic_parity_difference": round(float(demographic_parity_difference(y[mask], pred[mask], sensitive_features=s[mask])), 4),
            "equalized_odds_difference": round(float(equalized_odds_difference(y[mask], pred[mask], sensitive_features=s[mask])), 4)}
    # mitigation on the most disparate attribute: ThresholdOptimizer (equalized odds)
    worst = max(out["groups"], key=lambda g: out["groups"][g]["equalized_odds_difference"])
    s = te[worst].astype(str)
    keep = s.value_counts()[lambda v: v >= 500].index
    mask = s.isin(keep).values
    rng = np.random.RandomState(0)
    idx = np.where(mask)[0]
    tr_idx, ev_idx = idx[rng.rand(len(idx)) < 0.5], idx[rng.rand(len(idx)) >= 0.5]
    to = ThresholdOptimizer(estimator=_ScoreEstimator(), constraints="equalized_odds", objective="balanced_accuracy_score", prefit=True, predict_method="predict")
    to.fit(scores[tr_idx].reshape(-1, 1), y[tr_idx], sensitive_features=s.values[tr_idx])
    mit = to.predict(scores[ev_idx].reshape(-1, 1), sensitive_features=s.values[ev_idx], random_state=0)
    base = (scores[ev_idx] >= thr).astype(int)
    out["mitigation"] = {"attribute": worst, "before_eo_diff": round(float(equalized_odds_difference(y[ev_idx], base, sensitive_features=s.values[ev_idx])), 4),
                         "after_eo_diff": round(float(equalized_odds_difference(y[ev_idx], mit, sensitive_features=s.values[ev_idx])), 4),
                         "before_selection_rate": round(float(base.mean()), 4), "after_selection_rate": round(float(np.mean(mit)), 4),
                         "before_balanced_acc": round(_bal_acc(y[ev_idx], base), 4), "after_balanced_acc": round(_bal_acc(y[ev_idx], mit), 4)}
    return out


class _ScoreEstimator(BaseEstimator, ClassifierMixin):
    """Prefit 'estimator' that passes a precomputed risk score through (what ThresholdOptimizer needs)."""
    classes_ = np.array([0, 1])

    def fit(self, X, y=None):
        return self

    def predict(self, X):
        return np.asarray(X).reshape(-1)

    def __sklearn_is_fitted__(self):
        return True


def _bal_acc(y, p) -> float:
    tpr = float(((p == 1) & (y == 1)).sum() / max(1, (y == 1).sum()))
    tnr = float(((p == 0) & (y == 0)).sum() / max(1, (y == 0).sum()))
    return (tpr + tnr) / 2


def planted_bias(n: int = 20000, seeds: int = 20) -> dict:
    """Historic approval decisions with a known penalty `b` on protected group g=1. The model never sees g (fairness through
    unawareness) but sees a proxy correlated with it. A sound audit must flag b>0 and not flag b=0."""
    import lightgbm as lgb
    rows = []
    for b in (0.0, 0.3, 0.6, 1.0):
        for seed in range(seeds):
            rng = np.random.RandomState(seed)
            g = (rng.rand(n) < 0.3).astype(int)
            skill = rng.randn(n)                                   # true creditworthiness
            proxy = 0.9 * g + 0.6 * rng.randn(n)                   # e.g. neighbourhood: correlated with g, not causal
            approved = (skill - b * g + 0.5 * rng.randn(n) > 0).astype(int)
            qualified = (skill > 0).astype(int)                    # ground truth ability to repay
            X = np.c_[skill + 0.4 * rng.randn(n), proxy]
            tr, te = np.arange(n) < n // 2, np.arange(n) >= n // 2
            m = lgb.LGBMClassifier(n_estimators=80, learning_rate=0.1, verbose=-1, random_state=seed).fit(X[tr], approved[tr])
            pred = m.predict(X[te])
            dpd = demographic_parity_difference(qualified[te], pred, sensitive_features=g[te])
            eod = equalized_odds_difference(qualified[te], pred, sensitive_features=g[te])
            # permutation test for the selection-rate gap
            gap = abs(pred[g[te] == 1].mean() - pred[g[te] == 0].mean())
            perm = [abs(pred[(pp := rng.permutation(g[te])) == 1].mean() - pred[pp == 0].mean()) for _ in range(200)]
            rows.append({"bias": b, "seed": seed, "dpd": float(dpd), "eod": float(eod), "gap": float(gap), "p": float((np.array(perm) >= gap).mean())})
    d = pd.DataFrame(rows)
    summ = d.groupby("bias").agg(dpd=("dpd", "mean"), dpd_sd=("dpd", "std"), eod=("eod", "mean"), detected=("p", lambda p: float((p < 0.05).mean()))).round(4)
    return {"table": summ.reset_index().to_dict("records"), "n": n, "seeds": seeds}


def main() -> dict:
    a = proxy_audit()
    b = planted_bias()
    rows = []
    for g, d in a["groups"].items():
        rows.append({"attribute": g, "DPD": d["demographic_parity_difference"], "EO_diff": d["equalized_odds_difference"], "groups": len(d["by_group"])})
    md = ("# E3 (a)(b): fairness audit\n\n## (a) Proxy-group audit on real SBA test data (FY2017-19; decline = riskiest 20%)\n"
          f"AUC {a['auc']}, n={a['n']}, decision threshold PD>={a['threshold']}. Proxy groups are NOT protected classes.\n\n" + md_table(rows, ["attribute", "DPD", "EO_diff", "groups"])
          + f"\nMitigation (ThresholdOptimizer, equalized odds) on `{a['mitigation']['attribute']}`: {a['mitigation']}\n\n"
          + "## (b) Planted-bias detection (synthetic; model never sees the protected attribute)\n" + md_table(b["table"], ["bias", "dpd", "dpd_sd", "eod", "detected"]))
    save("e3_fairness_ab", {"proxy_audit": a, "planted_bias": b}, md)
    log_mlflow("wealthpilot-E3-fairness", "proxy_audit", {"threshold": a["threshold"]}, {"auc": a["auc"], **{f"eo_{g}": d["equalized_odds_difference"] for g, d in a["groups"].items()}})
    print(md)
    return {"a": a, "b": b}


if __name__ == "__main__":
    main()
