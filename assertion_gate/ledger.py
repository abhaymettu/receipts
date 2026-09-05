"""Receipt schema and session ledger: one receipt per tool call.

The field set is ported from nabaos `src/runtime/receipt.rs`. The HMAC signature,
the persisted key and the SQLite store are deliberately not ported - our receipts
are derived from a transcript the harness already wrote, so there is no gap
between minting and checking for a forger to sit in. See REUSE-MEMO.md.

A receipt is a plain dict so it serialises to JSONL for free. A ledger is a list
of them, in call order.
"""

import hashlib
import json

# Nothing here imports anything but stdlib: this module sits on the hook path.


def canon(obj):
    """Canonical JSON: sorted keys, no incidental whitespace.

    nabaos documents canonical-JSON input hashing but does not implement it -
    receipt.rs hashes whatever string the caller passes. We actually sort, so
    two identical calls hash identically regardless of key order.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest(value):
    if not isinstance(value, (str, bytes)):
        value = canon(value)
    if isinstance(value, str):
        value = value.encode("utf-8", "replace")
    return hashlib.sha256(value).hexdigest()


def make_receipt(id, tool_name, tool_input, output, result_count, facts,
                 timestamp_ms=0, is_error=False):
    """One tool call, reduced to what a claim can be checked against."""
    return {
        "id": id,
        "tool_name": tool_name,
        "input_hash": digest(tool_input),
        "output_hash": digest(output),
        "result_count": result_count,  # None when the tool has no countable result
        "facts": facts,                # deterministic key-values, per-tool
        "timestamp_ms": timestamp_ms,
        "is_error": is_error,
    }


def tools_used(ledger):
    return {r["tool_name"] for r in ledger}


def by_tool(ledger, tool_name):
    return [r for r in ledger if r["tool_name"] == tool_name]
