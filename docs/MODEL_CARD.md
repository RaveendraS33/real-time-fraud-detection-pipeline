# Model Card: `logreg-v1`

## Purpose

`logreg-v1` supplies a fraud probability to the local streaming detector. The detector combines
that probability with deterministic rules, retaining both values for auditability. It is a
portfolio demonstration, not a model approved for financial decisions.

## Training Data

- 20,000 deterministic synthetic transactions generated with seed `42`
- 8% target fraud rate
- First 80% used for training; final 20% held out for evaluation
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
| ROC AUC | 0.9902 |
| Average precision | 0.8890 |
| Precision at 0.5 | 0.6706 |
| Recall at 0.5 | 1.0000 |
| False positives | 168 |
| False negatives | 0 |

The high recall is intentional for an alerting system, but the false-positive count demonstrates
why human review and threshold tuning are necessary.

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
service to score without shipping scikit-learn in its container. CI retrains on Linux and checks
the contract, metrics, and coefficients with a small tolerance for platform-level floating-point
differences.
