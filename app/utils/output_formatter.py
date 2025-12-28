"""
Output formatter for converting extraction results to the required JSON schema.
"""

from typing import Dict, Any, List
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import OVERALL_CONFIDENCE_METHOD


def format_extraction_output(
    bureau_results: Dict[str, Any],
    gst_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    bureau_parameters = {}
    for param_id, result in bureau_results.items():
        bureau_parameters[param_id] = {
            "value": result.get("value"),
            "source": result.get("source"),
            "confidence": result.get("confidence", 0.0),
            "status": result.get("status", "extracted")
        }
        if "similarity_score" in result:
            bureau_parameters[param_id]["similarity_score"] = result["similarity_score"]
    gst_sales = []
    for sale in gst_results:
        gst_sales.append({
            "month": sale.get("month"),
            "sales": sale.get("sales"),
            "source": sale.get("source"),
            "confidence": sale.get("confidence", 0.0),
            "status": sale.get("status", "extracted")
        })
    
    # Calculate overall confidence score
    overall_confidence = calculate_overall_confidence(bureau_results, gst_results)
    
    return {
        "bureau_parameters": bureau_parameters,
        "gst_sales": gst_sales,
        "overall_confidence_score": overall_confidence
    }


def calculate_overall_confidence(
    bureau_results: Dict[str, Any],
    gst_results: List[Dict[str, Any]]
) -> float:
    confidences = []
    
    for result in bureau_results.values():
        conf = result.get("confidence", 0.0)
        if conf > 0:
            confidences.append(conf)
    
    for result in gst_results:
        conf = result.get("confidence", 0.0)
        if conf > 0:
            confidences.append(conf)
    
    if not confidences:
        return 0.0
    
    if OVERALL_CONFIDENCE_METHOD == "average":
        return round(sum(confidences) / len(confidences), 3)
    elif OVERALL_CONFIDENCE_METHOD == "minimum":
        return round(min(confidences), 3)
    else:
        return round(sum(confidences) / len(confidences), 3)


def print_formatted_output(output: Dict[str, Any]) -> None:

    import json
    print(json.dumps(output, indent=2))


def print_summary(output: Dict[str, Any]) -> None:

    print("\n" + "="*80)
    print("EXTRACTION SUMMARY")
    print("="*80)
    
    # Bureau parameters
    print("\n--- BUREAU PARAMETERS ---")
    for param_id, result in output["bureau_parameters"].items():
        status_icon = {
            "extracted": "✓",
            "not_found": "✗",
            "not_applicable": "○",
            "extraction_failed": "⚠"
        }.get(result["status"], "?")
        
        print(f"{status_icon} {param_id}: {result['value']}")
        print(f"   Source: {result['source']}, Confidence: {result['confidence']:.2f}")
    
    # GST sales
    print("\n--- GST SALES ---")
    for sale in output["gst_sales"]:
        status_icon = "✓" if sale["status"] == "extracted" else "✗"
        print(f"{status_icon} {sale['month']}: {sale['sales']}")
        print(f"   Source: {sale['source']}, Confidence: {sale['confidence']:.2f}")
    
    # Overall
    print(f"\n--- OVERALL CONFIDENCE: {output['overall_confidence_score']:.2f} ---")
    print("="*80 + "\n")

