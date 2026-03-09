#!/usr/bin/env python3
"""
Run adapter on 5 validation traces and output results.
"""

import json
from pathlib import Path
from agent_eval.adapters.generic_json import adapt

# Test traces
TRACES_DIR = Path(__file__).parent / "test-fixtures" / "validation"
TRACES = [
    "test_trace_1_realistic.json",
    "test_trace_2_determinism.json",
    "test_trace_3_cross_session.json",
    "test_trace_4_large_dirty.json",
    "test_trace_5_config_drift.json"
]

def extract_key_metrics(result):
    """Extract key metrics for validation."""
    return {
        "turn_count": len(result["turns"]),
        "run_confidence": result["metadata"]["run_confidence"],
        "segmentation_strategy": result["adapter_stats"]["segmentation_strategy"],
        "mapping_coverage": result["adapter_stats"]["mapping_coverage"],
        "total_events": result["adapter_stats"]["total_events_processed"],
        "dropped_events": result["adapter_stats"]["dropped_events_count"],
        "orphan_tool_results": len(result["adapter_stats"]["orphan_tool_results"]),
        "confidence_penalties": len(result["adapter_stats"]["confidence_penalties"]),
        "tool_calls": sum(1 for turn in result["turns"] for step in turn["steps"] if step["kind"] == "TOOL_CALL"),
        "tool_results": sum(1 for turn in result["turns"] for step in turn["steps"] if step["kind"] == "TOOL_RESULT"),
    }

def main():
    print("=" * 80)
    print("ADAPTER VALIDATION - 5 Production Traces")
    print("=" * 80)
    
    for trace_file in TRACES:
        trace_path = TRACES_DIR / trace_file
        print(f"\n{'=' * 80}")
        print(f"TRACE: {trace_file}")
        print(f"{'=' * 80}\n")
        
        try:
            # Run adapter
            result = adapt(str(trace_path))
            
            # Extract metrics
            metrics = extract_key_metrics(result)
            
            # Print summary
            print(f"✅ SUCCESS")
            print(f"\nKey Metrics:")
            print(f"  Turn Count: {metrics['turn_count']}")
            print(f"  Run Confidence: {metrics['run_confidence']:.3f}")
            print(f"  Segmentation Strategy: {metrics['segmentation_strategy']}")
            print(f"  Mapping Coverage: {metrics['mapping_coverage']:.3f}")
            print(f"  Total Events: {metrics['total_events']}")
            print(f"  Dropped Events: {metrics['dropped_events']}")
            print(f"  Tool Calls: {metrics['tool_calls']}")
            print(f"  Tool Results: {metrics['tool_results']}")
            print(f"  Orphan Tool Results: {metrics['orphan_tool_results']}")
            print(f"  Confidence Penalties: {metrics['confidence_penalties']}")
            
            # Print tool statuses
            print(f"\nTool Statuses:")
            for turn_idx, turn in enumerate(result["turns"]):
                tool_calls = [s for s in turn["steps"] if s["kind"] == "TOOL_CALL"]
                for tool in tool_calls:
                    status = tool.get("status", "unknown")
                    print(f"  Turn {turn_idx}: {tool['tool_name']} = {status}")
            
            # Print confidence penalties
            if result["adapter_stats"]["confidence_penalties"]:
                print(f"\nConfidence Penalties:")
                for penalty in result["adapter_stats"]["confidence_penalties"]:
                    print(f"  - {penalty['reason']}: {penalty['penalty']:.2f} ({penalty['location']})")
            
            # Save full output
            output_file = TRACES_DIR / f"{trace_file.replace('.json', '_output.json')}"
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n📄 Full output saved to: {output_file.name}")
            
        except Exception as e:
            print(f"❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'=' * 80}")
    print("VALIDATION COMPLETE")
    print(f"{'=' * 80}\n")

if __name__ == "__main__":
    main()
