# Model Card: `logreg-v1`

## Purpose

`logreg-v1` supplies a fraud probability to the local streaming detector. The detector combines
that probability with deterministic rules, retaining both values for auditability. It is a
portfolio demonstration, not a model approved for financial decisions.

## Training Data

- 20,000 deterministic synthetic transactions generated with seed `42`
- 8% target fraud rate
- First 70% for training, next 10% for probability calibration, final 20% held out for evaluation
- Fraud scenarios: high amount, foreign device, and low-value card testing
- Legitimate data includes occasional device replacements and high-value purchases to create
  overlap between classes

The `simulation.is_fraud` field is used only as the target. It and the scenario name are excluded
from the feature contract.

## Features

1. Log-transformed amount
2. Transaction count in the prior five-minute event-time window
3. New-device indicator
4. New-country indicator
5. Risky-merchant indicator

## Holdout Results

| Metric | Value |
| --- | ---: |
| ROC AUC | 0.9903 |
| Average precision | 0.8898 |
| Precision at 0.5 | 0.7896 |
| Recall at 0.5 | 0.8450 |
| False positives | 77 |
| False negatives | 53 |

Metrics are computed on the **calibrated** probabilities (see Calibration). Calibration trades some
recall at the fixed 0.5 threshold for well-calibrated probabilities and higher precision; recall can
be recovered by lowering the decision threshold, and the hybrid detector's deterministic rules add
coverage independent of the model score.

## Calibration

The served probabilities are **Platt-scaled**: a calibration sigmoid (`a`, `b`, stored in the
artifact's `calibration` field) is fit on the held-out 10% calibration split and applied to the raw
model logit at scoring time. Reproduce with `scripts/evaluate_model.py`.

| Metric | Before calibration | After (served) |
| --- | ---: | ---: |
| Brier score | 0.033 | 0.022 |
| Top-bin predicted vs observed | 0.63 vs 0.43 (over-confident) | 0.42 vs 0.43 (calibrated) |

Reliability after calibration (quantile bins, mean predicted -> observed fraud rate):

| Predicted | Observed |
| ---: | ---: |
| 0.000 | 0.000 |
| 0.000 | 0.000 |
| 0.001 | 0.000 |
| 0.003 | 0.000 |
| 0.424 | 0.427 |

Platt scaling removed the high-end over-confidence (the top bin now matches the observed fraud rate)
and improved the Brier score. The trade-off is lower recall at the fixed 0.5 threshold, since the
calibrated probabilities are less extreme; tune the threshold or rely on the hybrid rules to recover
coverage.

## Limitations

- Synthetic behavior is much simpler than real payment fraud.
- No demographic or protected attributes are used, but a real deployment would still require
  fairness, drift, calibration, and governance reviews.
- In-memory customer history is lost when the detector restarts.
- Holdout metrics reflect a warm feature state; a newly started detector has less customer
  history and therefore lower initial recall.
- Metrics must not be interpreted as expected production performance.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\train_model.py --samples 20000 --fraud-rate 0.08 --seed 42
```

The JSON artifact contains the scaler parameters and logistic coefficients, allowing the online
service to score without shipping scikit-learn in its container.

## Versioning and Governance

The model ships as a single versioned JSON artifact (`models/fraud_logreg_v1.json`) carrying
`model_version`, `artifact_version`, the feature contract, the scaler + coefficients, and the full
training configuration and metrics. Promotion is gated, not manual:

- **Reproducible training:** `scripts/train_model.py` is deterministic (fixed seed and split), so
  the artifact can be regenerated on any machine.
- **CI verification:** every push retrains on Linux and runs `scripts/verify_model_artifact.py`
  against the committed artifact. Contract fields (version, feature names, threshold, training
  config) must match exactly; model parameters must match within `rel_tol=1e-5, abs_tol=1e-7`
  (tight enough to catch a real model change, loose enough to tolerate cross-platform BLAS
  float differences); derived metrics within `abs_tol=5e-3` and confusion counts within `10`,
  because a sub-tolerance parameter drift can flip a borderline prediction.
- **Promotion:** ship a new model by training a new `model_version`, committing the new artifact,
  and updating this card. The detector loads the artifact at startup and refuses to start on a
  feature-contract mismatch, so an incompatible model cannot silently serve.
