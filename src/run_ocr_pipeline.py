"""
run_ocr_pipeline.py  — v2 (reuses existing LLM results)
───────────────────
Runs the full fraud detection pipeline on OCR-extracted claims
(from data/ocr_output/) and compares results against the EDI pipeline.

This script:
1. Loads all 1,300 OCR-extracted claims from data/ocr_output/
2. Runs rule-based checks on each claim
3. Runs LLM checks on claims that pass rules
4. Produces final verdicts
5. Computes F1, Precision, Recall vs ground truth
6. Prints a comparison table: OCR pipeline vs EDI pipeline

HOW TO RUN:
    python3 src/run_ocr_pipeline.py
"""

import json, sys, os
from pathlib import Path
from collections import defaultdict, Counter

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

OCR_DIR     = BASE_DIR / "data" / "ocr_output"
RULE_DIR    = BASE_DIR / "data" / "ocr_rule_results"
LLM_DIR     = BASE_DIR / "data" / "ocr_llm_results"
FINAL_DIR   = BASE_DIR / "data" / "ocr_final_results"
CLAIMS_JSON = BASE_DIR / "data" / "raw_claims" / "claims.json"
NCCI_PATH   = BASE_DIR / "data" / "ncci_edits.xlsx"

# EDI final results for comparison
EDI_FINAL   = BASE_DIR / "data" / "final_results" / "all_results.json"

for d in [RULE_DIR, LLM_DIR, FINAL_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def load_ground_truth():
    with open(CLAIMS_JSON) as f:
        claims = json.load(f)
    return {
        c["claim_id"]: {
            "fraud": c.get("fraud_indicator", False),
            "fraud_type": c.get("fraud_type", "Legitimate"),
        }
        for c in claims
    }


def safe_div(a, b):
    return a / b if b > 0 else 0.0


def compute_metrics(results):
    labeled = [r for r in results if r.get("true_fraud") is not None]
    tp = sum(1 for r in labeled if r["fraud_detected"] and r["true_fraud"])
    fp = sum(1 for r in labeled if r["fraud_detected"] and not r["true_fraud"])
    fn = sum(1 for r in labeled if not r["fraud_detected"] and r["true_fraud"])
    tn = sum(1 for r in labeled if not r["fraud_detected"] and not r["true_fraud"])
    p  = safe_div(tp, tp + fp)
    r  = safe_div(tp, tp + fn)
    f1 = safe_div(2 * p * r, p + r)
    return {"tp":tp,"fp":fp,"fn":fn,"tn":tn,
            "precision":round(p,3),"recall":round(r,3),
            "f1":round(f1,3),"total":len(labeled)}


def main():
    print("\nOCR FRAUD DETECTION PIPELINE")
    print("=" * 55)

    # ── Load dependencies ──────────────────────────────────────────────────────
    try:
        from rule_checks import RuleEngine
        from llm_checker import LLMChecker
    except ImportError as e:
        print(f"Import error: {e}")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  No ANTHROPIC_API_KEY — LLM checks will be skipped")

    # ── Load OCR claims ────────────────────────────────────────────────────────
    ocr_files = sorted(OCR_DIR.glob("*.json"))
    if not ocr_files:
        print(f"No OCR files found in {OCR_DIR}")
        print("Run extract_fields.py first.")
        sys.exit(1)

    print(f"\nLoaded {len(ocr_files):,} OCR-extracted claims")
    ground_truth = load_ground_truth()
    print(f"Loaded {len(ground_truth):,} ground truth labels")

    # ── Step 1: Rule checks ────────────────────────────────────────────────────
    print(f"\nStep 1: Running rule-based checks...")
    rule_engine = RuleEngine(ncci_path=NCCI_PATH)
    rule_flagged = 0

    for ocr_file in ocr_files:
        with open(ocr_file) as f:
            claim = json.load(f)
        result = rule_engine.check(claim)
        out_path = RULE_DIR / f"{ocr_file.stem}_rules.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        if result.get("fraud_detected"):
            rule_flagged += 1

    print(f"  Rule engine flagged {rule_flagged:,} claims")

    # ── Step 2: LLM checks ────────────────────────────────────────────────────
    print(f"\nStep 2: Running LLM checks (reusing existing results where available)...")
    llm_checked = llm_flagged = skipped = 0

    if api_key:
        llm_checker = LLMChecker()
        for ocr_file in ocr_files:
            claim_id = ocr_file.stem
            rule_path = RULE_DIR / f"{claim_id}_rules.json"
            with open(rule_path) as f:
                rule_result = json.load(f)

            if rule_result.get("fraud_detected"):
                # Already flagged by rules — skip LLM
                llm_result = {
                    "fraud_detected": True,
                    "fraud_type": rule_result.get("fraud_type"),
                    "confidence": "high",
                    "explanation": rule_result.get("explanation",""),
                    "skipped": True,
                    "checked_by": "rule_engine"
                }
                skipped += 1
            else:
                with open(ocr_file) as f:
                    claim = json.load(f)
                # Resume support — skip if already processed
                out_path_check = LLM_DIR / f"{claim_id}_llm.json"
                if out_path_check.exists():
                    with open(out_path_check) as f2:
                        llm_result = json.load(f2)
                    skipped += 1
                    continue

                llm_result = llm_checker.check(claim)
                llm_checked += 1
                if llm_result.get("fraud_detected"):
                    llm_flagged += 1

            out_path = LLM_DIR / f"{claim_id}_llm.json"
            with open(out_path, "w") as f:
                json.dump(llm_result, f, indent=2)

            if (llm_checked + skipped) % 100 == 0:
                print(f"  {llm_checked + skipped}/{len(ocr_files)} done...")
                sys.stdout.flush()

        print(f"  LLM checked {llm_checked:,} claims, flagged {llm_flagged:,}")
        print(f"  Skipped {skipped:,} (already caught by rules)")
    else:
        # No API key — write empty LLM results
        for ocr_file in ocr_files:
            claim_id = ocr_file.stem
            llm_result = {
                "fraud_detected": False, "fraud_type": None,
                "confidence": "low", "explanation": "LLM skipped — no API key",
                "checked_by": "skipped"
            }
            out_path = LLM_DIR / f"{claim_id}_llm.json"
            with open(out_path, "w") as f:
                json.dump(llm_result, f, indent=2)
        print("  LLM checks skipped (no API key)")

    # ── Step 3: Merge into final verdicts ──────────────────────────────────────
    print(f"\nStep 3: Generating final verdicts...")
    all_results = []

    for ocr_file in ocr_files:
        claim_id = ocr_file.stem
        gt = ground_truth.get(claim_id, {})

        rule_path = RULE_DIR / f"{claim_id}_rules.json"
        llm_path  = LLM_DIR  / f"{claim_id}_llm.json"

        with open(rule_path) as f: rule_result = json.load(f)
        with open(llm_path)  as f: llm_result  = json.load(f)

        rf = rule_result.get("fraud_detected", False)
        lf = llm_result.get("fraud_detected", False)
        lc = llm_result.get("confidence", "low")

        if rf:
            fraud_detected = True
            fraud_type     = rule_result.get("fraud_type")
            explanation    = rule_result.get("explanation","")
            decision_by    = "rule_engine"
        elif lf and lc in ["high","medium"]:
            fraud_detected = True
            fraud_type     = llm_result.get("fraud_type")
            explanation    = llm_result.get("explanation","")
            decision_by    = "llm_claude"
        else:
            fraud_detected = False
            fraud_type     = None
            explanation    = "All checks passed."
            decision_by    = "both"

        final = {
            "claim_id":      claim_id,
            "fraud_detected": fraud_detected,
            "fraud_type":    fraud_type,
            "explanation":   explanation,
            "decision_by":   decision_by,
            "true_fraud":    gt.get("fraud", None),
            "true_fraud_type": gt.get("fraud_type","Legitimate"),
            "rule_result":   rule_result,
            "llm_result":    llm_result,
        }
        all_results.append(final)

        # Save individual result
        out_path = FINAL_DIR / f"{claim_id}_final.json"
        with open(out_path, "w") as f:
            json.dump(final, f, indent=2)

    # Save combined
    with open(FINAL_DIR / "all_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    # ── Step 4: Compute metrics ────────────────────────────────────────────────
    ocr_metrics = compute_metrics(all_results)

    print(f"\n{'=' * 55}")
    print("  OCR PIPELINE RESULTS")
    print(f"{'=' * 55}")
    print(f"  F1 Score   : {ocr_metrics['f1']:.3f}  "
          f"{'✅ Target met' if ocr_metrics['f1'] >= 0.75 else '⚠️  Below target'}")
    print(f"  Precision  : {ocr_metrics['precision']:.3f}")
    print(f"  Recall     : {ocr_metrics['recall']:.3f}")
    print(f"  TP: {ocr_metrics['tp']}  FP: {ocr_metrics['fp']}  "
          f"FN: {ocr_metrics['fn']}  TN: {ocr_metrics['tn']}")

    # ── Step 5: Compare with EDI results ──────────────────────────────────────
    if EDI_FINAL.exists():
        with open(EDI_FINAL) as f:
            edi_results = json.load(f)
        edi_metrics = compute_metrics(edi_results)

        print(f"\n{'=' * 55}")
        print("  OCR vs EDI COMPARISON")
        print(f"{'=' * 55}")
        print(f"  {'Metric':<12} {'EDI Path':>10} {'OCR Path':>10} {'Difference':>12}")
        print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*12}")
        for metric in ["f1","precision","recall"]:
            edi_val = edi_metrics[metric]
            ocr_val = ocr_metrics[metric]
            diff    = ocr_val - edi_val
            sign    = "+" if diff >= 0 else ""
            print(f"  {metric.capitalize():<12} {edi_val:>10.3f} {ocr_val:>10.3f} "
                  f"{'':>4}{sign}{diff:.3f}")

        print(f"\n  EDI TP/FP/FN: {edi_metrics['tp']} / {edi_metrics['fp']} / {edi_metrics['fn']}")
        print(f"  OCR TP/FP/FN: {ocr_metrics['tp']} / {ocr_metrics['fp']} / {ocr_metrics['fn']}")

    print(f"\n  Results saved to: {FINAL_DIR}")
    print(f"\n  Next: review results and write Session 4 report")


if __name__ == "__main__":
    main()
