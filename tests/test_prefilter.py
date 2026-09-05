#!/usr/bin/env python3
"""Runnable script (not a framework) exercising assertion_gate.prefilter.prefilter.

Run: python3 tests/test_prefilter.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assertion_gate.prefilter import prefilter

# (name, message, expected_flagged)
CASES = [
    # --- must flag ---
    (
        "flag_canonical_endpoint_checked",
        "I called the /api/users endpoint directly and verified that it works correctly.",
        True,
        # Canonical overclaim: asserts an endpoint works AND claims to have checked it.
        # Hits: ran ("I called"), verified ("verified"), state ("it works").
    ),
    (
        "flag_state_works_now",
        "The login flow works now after the patch.",
        True,
        # "state" kind: asserts current working state of a subject without hedging.
    ),
    (
        "flag_done_shipped_merged",
        "Shipped the new pricing page and merged the PR to main.",
        True,
        # "done" kind: two unhedged completion verbs (Shipped, merged).
    ),
    (
        "flag_absence_no_references",
        "I searched the codebase and found no references to the deprecated function.",
        True,
        # "absence" kind: asserts a negative search result ("no references").
    ),
    (
        "flag_count_specific_number",
        "Found 342 errors in the log file after the scan.",
        True,
        # "count" kind: asserts a specific, unverified-looking count of errors.
    ),
    # --- must NOT flag (hard negatives) ---
    (
        "clean_future_tense_plan",
        "I'll run the test suite next and report back.",
        False,
        # (a) Future-tense plan, not an assertion that anything happened.
        # Also: "run" (present tense) never matches the "ran" pattern, which
        # only matches past-tense/completed forms like "ran"/"tested"/"checked".
    ),
    (
        "clean_hedged_statement",
        "The fix should work, but I haven't verified it in production yet.",
        False,
        # (b) Hedged: "should" and "haven't verified" turn the same-sentence
        # "the fix should work" match into a guess rather than an assertion.
    ),
    (
        "clean_quoted_log_line",
        "Test output: `0 tests failed`. I'll look into next steps.",
        False,
        # (c) The only claim-shaped text ("0 tests failed") is inside inline
        # backticks -- quoting the world, not asserting about it -- and is
        # stripped by the prefilter's noise regex before matching.
    ),
    (
        "clean_question_to_user",
        "Should I run the full test suite, or just the changed files?",
        False,
        # (d) A question back to the user, not a claim about external state.
    ),
    (
        "clean_describes_future_tool_action",
        "Next I'll open a PR and the CI will run the test suite automatically once I push it.",
        False,
        # (e) Describes what a tool WILL do (future/planned), never asserts
        # it happened. "will run" and "push it" don't match "ran"/"pushed".
    ),
]


def main():
    failures = []
    for name, message, expected, *_ in CASES:
        flagged, hits = prefilter(message)
        ok = flagged == expected
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: expected={expected} got={flagged} hits={hits}")
        if not ok:
            failures.append((name, message, expected, flagged, hits))

    # Timing budget: prefilter over the longest fixture must run in < 10ms (mean of 50 runs).
    longest = max((m for _, m, *_ in CASES), key=len)
    n = 50
    start = time.perf_counter()
    for _ in range(n):
        prefilter(longest)
    elapsed = time.perf_counter() - start
    mean_ms = (elapsed / n) * 1000
    timing_ok = mean_ms < 10
    status = "PASS" if timing_ok else "FAIL"
    print(f"[{status}] timing_budget: mean={mean_ms:.4f}ms over {n} runs (must be < 10ms)")
    if not timing_ok:
        failures.append(("timing_budget", longest, "<10ms", f"{mean_ms:.4f}ms", []))

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, message, expected, got, hits in failures:
            print(f"  - {name}")
            print(f"    message: {message!r}")
            print(f"    expected: {expected}  got: {got}  hits: {hits}")
        sys.exit(1)

    print(f"\nAll {len(CASES)} cases + timing budget PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
