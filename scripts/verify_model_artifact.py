"""CLI: verify a candidate model artifact against the committed one.

Thin wrapper around fraud_detection.model_artifact.verify so the comparison logic
lives in the application package (and is unit-tested) rather than in scripts/.
"""

import argparse
import json
from pathlib import Path

from fraud_detection.model_artifact import verify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("committed", type=Path)
    parser.add_argument("candidate", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    committed = json.loads(args.committed.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    errors = verify(committed, candidate)
    if errors:
        raise SystemExit("Model artifact verification failed: " + "; ".join(errors))
    print("Model artifact contract and values verified")


if __name__ == "__main__":
    main()
