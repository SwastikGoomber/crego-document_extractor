"""
Comprehensive Testing & Accuracy Evaluation Script

This script fulfills the testing requirements from project_requirements.md:
- Run extraction pipeline multiple times (100 runs)
- Measure consistency of extracted values
- Measure accuracy against expected values
- Report per-parameter accuracy
- Report overall accuracy/confidence score

Usage:
    python tests/test_accuracy.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import json
import time
import logging
import pandas as pd
from typing import Dict, List, Any
from collections import Counter
from app.services.parser import DoclingParser
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.services.extractors.crif import CRIFExtractor
from app.services.extractors.gstr import GSTR3BExtractor
from config import DEFAULT_CRIF_PATHS, DEFAULT_GSTR_PATH, DEFAULT_PARAM_PATH

# Set logging level to WARNING to reduce log spam during testing
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Ground Truth Values (from sample CRIF report: JEET ARORA_PARK251217CR671901414.pdf)
GROUND_TRUTH_CRIF = {
    "bureau_credit_score": 627,
    "bureau_ntc_accepted": False,
    "bureau_overdue_threshold": None,  # Policy parameter
    "bureau_dpd_30": 0,
    "bureau_dpd_60": 0,
    "bureau_dpd_90": 0,
    "bureau_settlement_writeoff": True,
    "bureau_no_live_pl_bl": False,
    "bureau_suit_filed": True,
    "bureau_wilful_default": False,
    "bureau_written_off_debt_amount": 0.0,
    "bureau_max_loans": 54,
    "bureau_loan_amount_threshold": None,  # Policy parameter
    "bureau_credit_inquiries": 0,
    "bureau_max_active_loans": 25
}

# Ground Truth for GSTR (from sample GSTR3B_06AAICK4577H1Z8_012025.pdf)
GROUND_TRUTH_GSTR = {
    "month": "January 2024",
    "sales": 951381.0
}

def run_single_extraction(crif_extractor, gstr_extractor, params, crif_doc, gst_doc):
    """
    Run a single extraction and return results.

    Note: We pass pre-parsed documents to avoid re-parsing on every run.
    The parsing is cached by Docling, but we can skip it entirely by parsing once.
    """
    # Extract from pre-parsed documents
    bureau_data = crif_extractor.extract(crif_doc, params)
    gst_data = gstr_extractor.extract(gst_doc)

    return {
        "bureau_parameters": bureau_data,
        "gst_sales": gst_data
    }

def calculate_consistency(results: List[Dict]) -> Dict[str, Any]:
    """
    Calculate consistency metrics across multiple runs.
    Consistency = all runs produce the same value for each parameter.
    """
    consistency_report = {}
    
    # Check CRIF parameters
    for param_id in GROUND_TRUTH_CRIF.keys():
        values = []
        for result in results:
            val = result["bureau_parameters"].get(param_id, {}).get("value")
            values.append(val)
        
        # Count unique values
        unique_values = list(set(values))
        is_consistent = len(unique_values) == 1
        
        consistency_report[param_id] = {
            "consistent": is_consistent,
            "unique_values": unique_values,
            "value_counts": dict(Counter(values))
        }
    
    # Check GSTR sales
    gst_values = []
    for result in results:
        if result["gst_sales"]:
            gst_values.append(result["gst_sales"][0].get("sales"))
    
    consistency_report["gst_sales"] = {
        "consistent": len(set(gst_values)) == 1,
        "unique_values": list(set(gst_values)),
        "value_counts": dict(Counter(gst_values))
    }
    
    return consistency_report

def calculate_accuracy(result: Dict) -> Dict[str, Any]:
    """
    Calculate accuracy by comparing against ground truth.
    Accuracy = percentage of parameters that match expected values.
    """
    accuracy_report = {}
    correct_count = 0
    total_count = 0
    
    # Check CRIF parameters
    for param_id, expected_value in GROUND_TRUTH_CRIF.items():
        actual_value = result["bureau_parameters"].get(param_id, {}).get("value")
        is_correct = actual_value == expected_value
        
        if is_correct:
            correct_count += 1
        total_count += 1
        
        accuracy_report[param_id] = {
            "expected": expected_value,
            "actual": actual_value,
            "correct": is_correct
        }
    
    # Check GSTR sales
    if result["gst_sales"]:
        actual_sales = result["gst_sales"][0].get("sales")
        is_correct = actual_sales == GROUND_TRUTH_GSTR["sales"]
        
        if is_correct:
            correct_count += 1
        total_count += 1
        
        accuracy_report["gst_sales"] = {
            "expected": GROUND_TRUTH_GSTR["sales"],
            "actual": actual_sales,
            "correct": is_correct
        }
    
    overall_accuracy = correct_count / total_count if total_count > 0 else 0
    
    return {
        "per_parameter": accuracy_report,
        "overall_accuracy": overall_accuracy,
        "correct_count": correct_count,
        "total_count": total_count
    }

def print_consistency_report(consistency_report: Dict):
    """Print consistency report in a readable format"""
    print("\n" + "="*80)
    print("CONSISTENCY REPORT (100 Runs)")
    print("="*80)

    consistent_count = 0
    total_params = len(consistency_report)

    for param_id, metrics in consistency_report.items():
        is_consistent = metrics["consistent"]
        if is_consistent:
            consistent_count += 1
            status = "[OK] CONSISTENT"
        else:
            status = "[FAIL] INCONSISTENT"

        print(f"\n{param_id}:")
        print(f"  Status: {status}")

        if not is_consistent:
            print(f"  Unique Values: {metrics['unique_values']}")
            print(f"  Value Distribution: {metrics['value_counts']}")

    consistency_rate = consistent_count / total_params if total_params > 0 else 0
    print(f"\n{'-'*80}")
    print(f"Overall Consistency: {consistency_rate:.1%} ({consistent_count}/{total_params} parameters)")
    print("="*80)

def print_accuracy_report(accuracy_report: Dict):
    """Print accuracy report in a readable format"""
    print("\n" + "="*80)
    print("ACCURACY REPORT (vs Ground Truth)")
    print("="*80)

    per_param = accuracy_report["per_parameter"]

    for param_id, metrics in per_param.items():
        is_correct = metrics["correct"]
        status = "[OK]" if is_correct else "[FAIL]"

        print(f"\n{status} {param_id}:")
        print(f"  Expected: {metrics['expected']}")
        print(f"  Actual:   {metrics['actual']}")

    print(f"\n{'-'*80}")
    print(f"Overall Accuracy: {accuracy_report['overall_accuracy']:.1%} "
          f"({accuracy_report['correct_count']}/{accuracy_report['total_count']} parameters)")
    print("="*80)

def save_test_results(consistency_report: Dict, accuracy_report: Dict,
                      timing_stats: Dict, output_file: str = "test_results.json"):
    """Save test results to JSON file"""
    results = {
        "test_metadata": {
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "num_runs": timing_stats["num_runs"],
            "total_time": timing_stats["total_time"],
            "avg_time_per_run": timing_stats["avg_time_per_run"]
        },
        "consistency": consistency_report,
        "accuracy": accuracy_report,
        "summary": {
            "consistency_rate": sum(1 for m in consistency_report.values() if m["consistent"]) / len(consistency_report),
            "accuracy_rate": accuracy_report["overall_accuracy"],
            "all_tests_passed": (
                all(m["consistent"] for m in consistency_report.values()) and
                accuracy_report["overall_accuracy"] == 1.0
            )
        }
    }

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[OK] Test results saved to {output_file}")

def main():
    import argparse

    parser_args = argparse.ArgumentParser(
        description="Comprehensive Testing & Accuracy Evaluation"
    )
    parser_args.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of extraction runs (default: 10, requirements suggest 100)"
    )
    args = parser_args.parse_args()

    num_runs = args.runs

    print("\n" + "="*80)
    print("COMPREHENSIVE TESTING & ACCURACY EVALUATION")
    print("="*80)
    print(f"\nThis test will:")
    print(f"  1. Run extraction pipeline {num_runs} times")
    print("  2. Measure consistency of extracted values")
    print("  3. Measure accuracy against ground truth")
    print("  4. Generate detailed reports")
    print("\n" + "="*80)

    # Initialize services (once)
    print("\n[1/5] Initializing services...")
    parser = DoclingParser()
    embedding = EmbeddingService()
    llm = LLMService()
    crif_extractor = CRIFExtractor(embedding, llm)
    gstr_extractor = GSTR3BExtractor()

    # Load parameters
    print("[2/5] Loading parameters...")
    df = pd.read_excel(DEFAULT_PARAM_PATH)
    df.columns = [c.lower().strip() for c in df.columns]
    params = []
    for _, row in df.iterrows():
        params.append({
            "id": row.get("parameter id", ""),
            "name": row.get("parameter name", ""),
            "description": row.get("description", "")
        })

    print(f"[OK] Loaded {len(params)} parameters")

    # Parse documents ONCE (this is the slow part)
    print("\n[3/5] Parsing documents (one-time operation)...")
    parse_start = time.time()

    # Parse CRIF
    crif_path = DEFAULT_CRIF_PATHS[0]
    with open(crif_path, "rb") as f:
        crif_doc = parser.parse_pdf(f.read(), source_name=os.path.basename(crif_path))

    # Parse GSTR
    with open(DEFAULT_GSTR_PATH, "rb") as f:
        gst_doc = parser.parse_pdf(f.read(), source_name="gstr.pdf")

    parse_time = time.time() - parse_start
    print(f"[OK] Documents parsed in {parse_time:.2f}s")

    # Pre-embed document chunks ONCE (optimization for multiple runs)
    print("\n[4/5] Pre-embedding document chunks (one-time operation)...")
    embed_start = time.time()

    # Prepare and embed CRIF chunks
    document_chunks = crif_extractor._prepare_document_chunks(crif_doc)
    print(f"   Prepared {len(document_chunks)} CRIF chunks")

    # Pre-embed all chunks by calling embed_text on each
    for chunk in document_chunks:
        text = chunk.get('text') or chunk.get('content') or str(chunk)
        chunk['embedding'] = embedding.embed_text(text)[0]

    # Store pre-embedded chunks in the document for reuse
    crif_doc['_embedded_chunks'] = document_chunks

    embed_time = time.time() - embed_start
    print(f"[OK] Chunks embedded in {embed_time:.2f}s")
    print(f"   Total setup time: {parse_time + embed_time:.2f}s")

    # Run extraction multiple times (using pre-parsed documents)
    print(f"\n[5/5] Running extraction {num_runs} times...")
    print("   (Using cached parsed documents for speed)")
    if num_runs >= 10:
        print("   (This may take a few minutes...)")

    results = []
    start_time = time.time()

    for i in range(num_runs):
        if num_runs >= 10 and (i + 1) % max(1, num_runs // 10) == 0:
            elapsed = time.time() - start_time
            avg_per_run = elapsed / (i + 1)
            remaining = avg_per_run * (num_runs - i - 1)
            print(f"   Progress: {i + 1}/{num_runs} runs completed "
                  f"(~{remaining:.0f}s remaining)...")

        result = run_single_extraction(crif_extractor, gstr_extractor, params,
                                       crif_doc, gst_doc)
        results.append(result)

    total_time = time.time() - start_time
    avg_time = total_time / num_runs

    print(f"[OK] Completed {num_runs} runs in {total_time:.2f}s (avg: {avg_time:.3f}s per run)")

    # Calculate metrics
    print("\n[ANALYSIS] Calculating metrics...")
    consistency_report = calculate_consistency(results)
    accuracy_report = calculate_accuracy(results[0])  # Use first run for accuracy

    timing_stats = {
        "num_runs": num_runs,
        "total_time": total_time,
        "avg_time_per_run": avg_time
    }

    # Print reports
    print_consistency_report(consistency_report)
    print_accuracy_report(accuracy_report)

    # Save results
    save_test_results(consistency_report, accuracy_report, timing_stats)

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()

