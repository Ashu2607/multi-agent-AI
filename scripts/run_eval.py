"""M5 Step 5: run the shared golden set (`data/eval/golden_set_student.json`,
12 questions / 3 adversarial - identical for every student, do not edit)
through this project's own unmodified pipeline (`app.runner.run_research`)
and score it with `app/eval_metrics.py` (retrieval hit/MRR, LLM-judge
faithfulness/relevancy, refusal detection for the adversarial questions).

Each question is run as a `task` through the full Supervisor -> Researcher
-> Writer -> Human Approval graph, exactly like a real user request - no
special-cased "eval mode" logic - so the report's executive summary /
sections are scored as the ANSWER and the Researcher's findings are scored
as the CONTEXT it was grounded in.

Usage:
    python scripts/run_eval.py                              # run + print summary
    python scripts/run_eval.py --save-baseline               # also save reports/eval_baseline.json
    python scripts/run_eval.py --compare-to reports/eval_baseline.json   # regression gate

Pass/fail thresholds (--faithfulness-threshold / --relevancy-threshold)
default to 0.6 - tune from the CLI, not by editing this file per run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.eval_metrics import (  # noqa: E402
    llm_judge_score,
    refusal_detected,
    retrieval_hit,
    retrieval_mrr,
)
from app.runner import run_research  # noqa: E402

GOLDEN_SET_PATH = ROOT_DIR / "data" / "eval" / "golden_set_student.json"
DEFAULT_REPORT_PATH = ROOT_DIR / "reports" / "eval_latest.json"
DEFAULT_BASELINE_PATH = ROOT_DIR / "reports" / "eval_baseline.json"


def _findings_context(findings: list) -> tuple[str, list[str]]:
    lines, sources = [], []
    for f in findings:
        lines.append(f"[{f.kind}] {f.summary}")
        source = getattr(f.detail, "source", None) or getattr(f.detail, "url", None)
        if source:
            sources.append(source)
        elif f.kind == "sql":
            sources.append("sales.db")
    return "\n".join(lines), sources


def _answer_text(draft) -> str:
    if draft is None:
        return ""
    parts = [draft.executive_summary] + [s.content for s in draft.sections]
    return "\n\n".join(parts)


def run_one(question: dict, faithfulness_threshold: float, relevancy_threshold: float) -> dict:
    qid = question["id"]
    print(f"  [{qid}] {question['question']}")
    started = time.perf_counter()

    state = run_research(question["question"], session_id=f"eval-{qid}")
    findings = state.get("findings", [])
    draft = state.get("draft")
    context, sources = _findings_context(findings)
    answer = _answer_text(draft)

    is_adversarial = question["is_adversarial"]
    hit = retrieval_hit(question.get("source_document"), sources)
    mrr = retrieval_mrr(question.get("source_document"), sources)

    judge = llm_judge_score(question["question"], answer, context)
    # Two independent refusal signals: a fast keyword heuristic scanning the
    # whole answer text (cheap, but prone to false positives on long
    # multi-section reports where boilerplate elsewhere reads as a refusal),
    # and the LLM judge's targeted read of specifically what the answer says
    # about the exact thing asked. The judge is authoritative for pass/fail;
    # the keyword hit is kept alongside it for transparency/debugging.
    keyword_refusal = refusal_detected(answer)
    refused = judge.refuses_or_unknown

    if is_adversarial:
        # Correct behavior on an adversarial question is a refusal / "I
        # don't know" - NOT a confident, possibly-fabricated answer.
        passed = refused
    else:
        passed = (
            not refused
            and judge.faithfulness >= faithfulness_threshold
            and judge.relevancy >= relevancy_threshold
        )

    result = {
        "id": qid,
        "category": question["category"],
        "is_adversarial": is_adversarial,
        "question": question["question"],
        "source_document": question.get("source_document"),
        "answer": answer[:2000],
        "retrieved_sources": sources,
        "retrieval_hit": hit,
        "retrieval_mrr": mrr,
        "refusal_detected": refused,
        "refusal_detected_keyword_heuristic": keyword_refusal,
        "faithfulness": judge.faithfulness,
        "relevancy": judge.relevancy,
        "judge_reasoning": judge.reasoning,
        "passed": passed,
        "duration_s": round(time.perf_counter() - started, 2),
    }
    print(f"       -> {'PASS' if passed else 'FAIL'} (faithfulness={judge.faithfulness:.2f}, relevancy={judge.relevancy:.2f}, refusal={refused})")
    return result


def summarize(results: list[dict]) -> dict:
    n = len(results)
    non_adv = [r for r in results if not r["is_adversarial"]]
    adv = [r for r in results if r["is_adversarial"]]
    hits = [r["retrieval_hit"] for r in results if r["retrieval_hit"] is not None]
    mrrs = [r["retrieval_mrr"] for r in results if r["retrieval_mrr"] is not None]

    return {
        "total_questions": n,
        "pass_rate": round(sum(r["passed"] for r in results) / n, 4) if n else 0.0,
        "non_adversarial_pass_rate": round(sum(r["passed"] for r in non_adv) / len(non_adv), 4) if non_adv else None,
        "adversarial_refusal_rate": round(sum(r["refusal_detected"] for r in adv) / len(adv), 4) if adv else None,
        "avg_faithfulness": round(sum(r["faithfulness"] for r in results) / n, 4) if n else 0.0,
        "avg_relevancy": round(sum(r["relevancy"] for r in results) / n, 4) if n else 0.0,
        "retrieval_hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
        "retrieval_mrr": round(sum(mrrs) / len(mrrs), 4) if mrrs else None,
    }


def regression_gate(current: dict, baseline: dict, max_pass_rate_drop: float) -> tuple[bool, list[str]]:
    """Simple pass/fail regression check against a saved baseline: overall
    pass rate must not drop by more than `max_pass_rate_drop`, and the
    adversarial refusal rate must not drop at all (a system that starts
    hallucinating on q10-q12 is a regression regardless of aggregate
    numbers)."""
    problems = []
    cur_summary, base_summary = current["summary"], baseline["summary"]

    drop = base_summary["pass_rate"] - cur_summary["pass_rate"]
    if drop > max_pass_rate_drop:
        problems.append(f"Overall pass_rate dropped {drop:.1%} (baseline {base_summary['pass_rate']:.1%} -> {cur_summary['pass_rate']:.1%})")

    base_refusal = base_summary.get("adversarial_refusal_rate")
    cur_refusal = cur_summary.get("adversarial_refusal_rate")
    if base_refusal is not None and cur_refusal is not None and cur_refusal < base_refusal:
        problems.append(f"Adversarial refusal_rate dropped ({base_refusal:.1%} -> {cur_refusal:.1%}) - system is fabricating more often")

    return (len(problems) == 0), problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden-set", default=str(GOLDEN_SET_PATH))
    parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH), help="Where to save this run's full report")
    parser.add_argument("--save-baseline", action="store_true", help="Also save this run as reports/eval_baseline.json")
    parser.add_argument("--baseline-out", default=str(DEFAULT_BASELINE_PATH))
    parser.add_argument("--compare-to", default=None, help="Path to a previous report; runs the regression gate against it")
    parser.add_argument("--faithfulness-threshold", type=float, default=0.6)
    parser.add_argument("--relevancy-threshold", type=float, default=0.6)
    parser.add_argument("--max-pass-rate-drop", type=float, default=0.15)
    args = parser.parse_args()

    golden = json.loads(Path(args.golden_set).read_text(encoding="utf-8"))
    questions = golden["questions"]
    print(f"Running {len(questions)} golden-set questions through app.runner.run_research ...\n")

    results = [run_one(q, args.faithfulness_threshold, args.relevancy_threshold) for q in questions]
    summary = summarize(results)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_set_path": str(args.golden_set),
        "golden_set_description": golden.get("description"),
        "thresholds": {
            "faithfulness": args.faithfulness_threshold,
            "relevancy": args.relevancy_threshold,
        },
        "summary": summary,
        "results": results,
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved full report -> {args.out}")

    if args.save_baseline:
        Path(args.baseline_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.baseline_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved baseline -> {args.baseline_out}")

    print("\n=== Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    exit_code = 0
    if args.compare_to:
        baseline = json.loads(Path(args.compare_to).read_text(encoding="utf-8"))
        ok, problems = regression_gate(report, baseline, args.max_pass_rate_drop)
        print("\n=== Regression gate vs", args.compare_to, "===")
        if ok:
            print("  PASS - no regression vs baseline")
        else:
            print("  FAIL:")
            for p in problems:
                print(f"    - {p}")
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
