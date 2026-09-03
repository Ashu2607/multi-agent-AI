# bias_audit.py -- checks loan_approval_data.csv for unfair treatment
# between two applicant groups, using AIF360.
#
# This is the FILLED-IN version (verified against a real AIF360 install,
# 13 Aug 2026 -- see MS6_Demo_Build_Guide.md Step 5 for the confirmed
# output). Students got the fill-in-the-TODO version of this same file on
# 10 Aug; this is provided here as the working answer for the trainer's
# own dry-run, not to hand to students in place of their own exercise.

import pandas as pd
from aif360.datasets import BinaryLabelDataset
from aif360.metrics import BinaryLabelDatasetMetric, ClassificationMetric
import json

df = pd.read_csv("loan_approval_data.csv")

# AIF360 needs numbers, not text, for the protected attribute.
# CampusA = 0 (the "privileged" group in this dataset -- historically
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

# Part A: is the MODEL's decision pattern fair?
metric_pred = BinaryLabelDatasetMetric(
    dataset_pred,
    privileged_groups=privileged_groups,
    unprivileged_groups=unprivileged_groups,
)
disparate_impact = metric_pred.disparate_impact()
statistical_parity_difference = metric_pred.statistical_parity_difference()

# Part B: compare the model's predictions AGAINST what actually happened
class_metric = ClassificationMetric(
    dataset_true,
    dataset_pred,
    privileged_groups=privileged_groups,
    unprivileged_groups=unprivileged_groups,
)
equal_opportunity_difference = class_metric.equal_opportunity_difference()

results = {
    "disparate_impact": round(disparate_impact, 3),
    "statistical_parity_difference": round(statistical_parity_difference, 3),
    "equal_opportunity_difference": round(equal_opportunity_difference, 3),
    "campusA_approval_rate": round(
        df[df.campus_group == "CampusA"]["loan_approved_model_prediction"].mean(), 3
    ),
    "campusB_approval_rate": round(
        df[df.campus_group == "CampusB"]["loan_approved_model_prediction"].mean(), 3
    ),
}

print(json.dumps(results, indent=2))

with open("bias_audit_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nSaved to bias_audit_results.json")
