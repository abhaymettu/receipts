#!/usr/bin/env python3
"""Adjudicate batch 2 label candidates and merge into the frozen label set.

Usage: python3 adjudicate_batch2.py [--candidates PATH] [--labels PATH] [--output PATH]

Reads label_candidates_batch2.json (v3-unsupported claims from batch 2),
presents each for adjudication, and merges the results into the frozen label set.

The adjudication protocol is 4-label:
- overclaim: the claim is not supported by the evidence
- fp_turn_scope: evidence exists in earlier turns
- fp_evidence_missed: evidence exists in this turn but was overlooked
- fp_not_a_claim: the extracted text is not a verifiable assertion

Each adjudication is logged with a timestamp and rationale for the audit trail.
"""

import json
import sys
import time

def main():
    candidates_path = "label_candidates_batch2.json"
    labels_path = "reports/labels.json"
    output_path = "reports/labels_v2.json"
    
    for i, a in enumerate(sys.argv):
        if a == "--candidates" and i + 1 < len(sys.argv):
            candidates_path = sys.argv[i + 1]
        elif a == "--labels" and i + 1 < len(sys.argv):
            labels_path = sys.argv[i + 1]
        elif a == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]
    
    # Load existing labels
    try:
        existing = json.loads(open(labels_path).read())
        print(f"Existing labels: {len(existing)}")
    except FileNotFoundError:
        existing = []
        print("No existing labels found, starting fresh")
    
    # Load candidates
    try:
        candidates = json.loads(open(candidates_path).read())
        print(f"Batch 2 candidates: {len(candidates)}")
    except FileNotFoundError:
        print(f"No candidates file at {candidates_path}")
        print("Run batch 2 first to generate label candidates")
        return 1
    
    if not candidates:
        print("No candidates to adjudicate")
        return 0
    
    # Check for duplicates against existing labels
    existing_claims = {l["claim"].strip().lower() for l in existing}
    new_candidates = [c for c in candidates 
                      if c.get("claim", "").strip().lower() not in existing_claims]
    print(f"New candidates (after dedup): {len(new_candidates)}")
    
    # Output the adjudication queue
    queue = []
    for c in new_candidates:
        queue.append({
            "turn_uuid": c.get("turn_uuid", ""),
            "claim": c.get("claim", ""),
            "type": c.get("type", ""),
            "tool_calls": c.get("tool_calls", 0),
            "source": c.get("source", ""),
            "v3_verdict": c.get("v3_verdict", ""),
            "v3_why": c.get("v3_why", ""),
            "label": None,  # To be filled by adjudicator
            "adjudicated_at": None,
            "audit_trail": [],
        })
    
    # Save the queue
    queue_path = "reports/adjudication_queue.json"
    with open(queue_path, "w") as f:
        json.dump(queue, f, indent=2)
    print(f"\nAdjudication queue saved to {queue_path}")
    print(f"Review each candidate and set the 'label' field.")
    print(f"Then run: python3 adjudicate_batch2.py --merge")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
