"""
compare_results.py
------------------
Compares model detection results against ground truth annotations.
Calculates precision, recall, F1 score per letter and overall.
Produces a detailed comparison report.

Usage:
    python compare_results.py --ground_truth ground_truth.json --results results_claude.json --output comparison_claude.json
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalise(text):
    """Normalise text for comparison — lowercase, strip whitespace."""
    return text.strip().lower()


def texts_match(gt_text, pred_text):
    """
    Check if ground truth and predicted text match.
    Handles partial matches where one contains the other
    (e.g. 'hverken har lyst eller' vs 'hverken har lyst eller evne').
    """
    gt = normalise(gt_text)
    pred = normalise(pred_text)
    # Exact match
    if gt == pred:
        return "exact"
    # Partial match — one contains the other
    if gt in pred or pred in gt:
        return "partial"
    # Word overlap — check if majority of words match
    gt_words = set(gt.split())
    pred_words = set(pred.split())
    if len(gt_words) > 0:
        overlap = len(gt_words & pred_words) / len(gt_words)
        if overlap >= 0.75:
            return "partial"
    return None


def compare_letter(gt_underlinings, pred_underlinings):
    """Compare ground truth and predicted underlinings for one letter."""
    matched_gt = set()
    matched_pred = set()
    match_details = []

    for i, gt in enumerate(gt_underlinings):
        for j, pred in enumerate(pred_underlinings):
            if j in matched_pred:
                continue
            match_type = texts_match(gt["text"], pred["text"])
            if match_type:
                matched_gt.add(i)
                matched_pred.add(j)
                match_details.append({
                    "gt_text": gt["text"],
                    "pred_text": pred["text"],
                    "match_type": match_type,
                    "gt_confidence": gt.get("confidence", ""),
                    "pred_confidence": pred.get("confidence", "")
                })
                break

    # False negatives — in ground truth but not found by model
    false_negatives = [
        gt_underlinings[i] for i in range(len(gt_underlinings))
        if i not in matched_gt
    ]

    # False positives — found by model but not in ground truth
    false_positives = [
        pred_underlinings[j] for j in range(len(pred_underlinings))
        if j not in matched_pred
    ]

    tp = len(matched_gt)
    fp = len(false_positives)
    fn = len(false_negatives)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "matches": match_details,
        "missed": [fn["text"] for fn in false_negatives],
        "extra": [fp["text"] for fp in false_positives]
    }


def main():
    p = argparse.ArgumentParser(description="Compare detection results against ground truth.")
    p.add_argument("--ground_truth", required=True, help="Ground truth JSON file")
    p.add_argument("--results", required=True, help="Model results JSON file")
    p.add_argument("--output", default="comparison.json", help="Output comparison report")
    args = p.parse_args()

    gt_data = load_json(args.ground_truth)
    results_data = load_json(args.results)

    # Build lookup dicts
    gt_by_file = {entry["file"]: entry["underlinings"] for entry in gt_data["ground_truth"]}
    results_by_file = {entry["file"]: entry["underlinings"] for entry in results_data["results"]}

    model_name = results_data.get("model_used", "unknown")
    print(f"Model: {model_name}")
    print(f"Ground truth letters: {len(gt_by_file)}")
    print(f"Results letters: {len(results_by_file)}")
    print()

    all_files = sorted(set(gt_by_file.keys()) | set(results_by_file.keys()))
    letter_results = []
    total_tp = total_fp = total_fn = 0

    for filename in all_files:
        gt_underlinings = gt_by_file.get(filename, [])
        pred_underlinings = results_by_file.get(filename, [])

        comparison = compare_letter(gt_underlinings, pred_underlinings)
        comparison["file"] = filename

        total_tp += comparison["true_positives"]
        total_fp += comparison["false_positives"]
        total_fn += comparison["false_negatives"]

        letter_results.append(comparison)

        # Print summary per letter
        status = "✓" if comparison["false_positives"] == 0 and comparison["false_negatives"] == 0 else "!"
        print(f"  {status} {filename}")
        print(f"    TP:{comparison['true_positives']} FP:{comparison['false_positives']} FN:{comparison['false_negatives']} | P:{comparison['precision']} R:{comparison['recall']} F1:{comparison['f1']}")
        if comparison["missed"]:
            print(f"    Missed: {comparison['missed']}")
        if comparison["extra"]:
            print(f"    Extra:  {comparison['extra']}")

    # Overall scores
    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    overall_f1 = 2 * overall_precision * overall_recall / (overall_precision + overall_recall) if (overall_precision + overall_recall) > 0 else 0

    print()
    print("=" * 50)
    print(f"OVERALL RESULTS — {model_name}")
    print(f"  True Positives:  {total_tp}")
    print(f"  False Positives: {total_fp}")
    print(f"  False Negatives: {total_fn}")
    print(f"  Precision:       {round(overall_precision, 3)}")
    print(f"  Recall:          {round(overall_recall, 3)}")
    print(f"  F1 Score:        {round(overall_f1, 3)}")
    print("=" * 50)

    output = {
        "model_used": model_name,
        "overall": {
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "precision": round(overall_precision, 3),
            "recall": round(overall_recall, 3),
            "f1": round(overall_f1, 3)
        },
        "by_letter": letter_results
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetailed report saved to {output_path}")


if __name__ == "__main__":
    main()
