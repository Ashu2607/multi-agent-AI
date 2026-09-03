"""AIF360 bias audit (M6 Step 5 / Category 6-7 evidence).

Checks `data/bias_audit/loan_approval_data.csv` for unfair treatment
between two applicant groups (CampusA = privileged, CampusB =
unprivileged). This is the trainer-provided shared dataset referenced by
the M6 build guide - copied verbatim into this repo from
`ms6_cloudrun_demo/loan_approval_data.csv` so the audit runs against the
same numbers every student's cohort was given, not an invented one.

This step doesn't touch the deployed app at all - it demonstrates the
AIF360 method against a fixed dataset built to show a clear, real gap on
purpose. Getting a large disparate impact / statistical parity gap below
is the *expected*, correct outcome of running this audit, not a bug.

Run with (from repo root, after `pip install -r requirements.txt`):
    python scripts/bias_audit.py

Writes `reports/bias_audit_results.json` and prints the same JSON to
stdout so the numbers can be pasted straight into the Model Card / NIST
worksheet (Categories 6 and 7).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from aif360.datasets import BinaryLabelDataset
from aif360.metrics import BinaryLabelDatasetMetric, ClassificationMetric

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT_DIR / "data" / "bias_audit" / "loan_approval_data.csv"
OUT_PATH = ROOT_DIR / "reports" / "bias_audit_results.json"


def main() -> None:
    df = pd.read_csv(DATA_PATH)

    # AIF360 needs numbers, not text, for the protected attribute.
    # CampusA = 0 (the "privileged" group in this dataset - historically
    # approved more often), CampusB = 1 (the "unprivileged" group).
    df["group_numeric"] = df["campus_group"].map({"CampusA": 0, "CampusB": 1})

    privileged_groups = [{"group_numeric": 0}]
    unprivileged_groups = [{"group_numeric": 1}]

    df_true = df[["group_numeric", "loan_approved_actual"]].rename(
        columns={"loan_approved_actual": "label"}
    )
    df_pred = df[["group_numeric", "loan_approved_model_prediction"]].rename(
        columns={"loan_approved_model_prediction": "label"}
    )

    dataset_true = BinaryLabelDataset(
        df=df_true,
        label_names=["label"],
        protected_attribute_names=["group_numeric"],
        favorable_label=1,
        unfavorable_label=0,
    )
    dataset_pred = BinaryLabelDataset(
        df=df_pred,
        label_names=["label"],
        protected_attribute_names=["group_numeric"],
        favorable_label=1,
        unfavorable_label=0,
    )

    # Part A: is the model's decision pattern fair, on its own?
    metric_pred = BinaryLabelDatasetMetric(
        dataset_pred,
        privileged_groups=privileged_groups,
        unprivileged_groups=unprivileged_groups,
    )
    disparate_impact = metric_pred.disparate_impact()
    statistical_parity_difference = metric_pred.statistical_parity_difference()

    # Part B: compare the model's predictions against what actually happened.
    class_metric = ClassificationMetric(
        dataset_true,
        dataset_pred,
        privileged_groups=privileged_groups,
        unprivileged_groups=unprivileged_groups,
    )
    equal_opportunity_difference = class_metric.equal_opportunity_difference()

    results = {
        "dataset": str(DATA_PATH.relative_to(ROOT_DIR)),
        "n_rows": len(df),
        "disparate_impact": round(disparate_impact, 3),
        "statistical_parity_difference": round(statistical_parity_difference, 3),
        "equal_opportunity_difference": round(equal_opportunity_difference, 3),
        "campusA_approval_rate": round(
            df[df.campus_group == "CampusA"]["loan_approved_model_prediction"].mean(), 3
        ),
        "campusB_approval_rate": round(
            df[df.campus_group == "CampusB"]["loan_approved_model_prediction"].mean(), 3
        ),
        "interpretation_notes": [
            "disparate_impact: ratio, 1.0 = equal approval rates. The 'four-fifths "
            "rule' treats anything below 0.8 as a red flag.",
            "statistical_parity_difference: same comparison as a raw gap instead "
            "of a ratio; 0 = equal rates.",
            "equal_opportunity_difference: among equally-qualified applicants "
            "(same true label), does one group still get approved less often? "
            "0 = equal treatment for equal qualification - this is the number "
            "that can't be explained away by 'maybe that group applies less'.",
        ],
    }

    print(json.dumps(results, indent=2))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {OUT_PATH.relative_to(ROOT_DIR)}")
    print(
        "\nThis audit runs against the shared loan_approval_data.csv, not this "
        "app's own /research pipeline - it demonstrates the AIF360 method. "
        "Write your own one-paragraph verdict on these numbers for the Model "
        "Card / NIST worksheet; don't just paste the JSON."
    )


if __name__ == "__main__":
    main()
