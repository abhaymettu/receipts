"""Labels the scorer is allowed to use.

Two orthogonal axes, both ported by name from prior art (see REUSE-MEMO.md):

  TYPES    the six hallucination types from the NyayaVerifyBench paper, kept
           verbatim so a per-type table here lines up with theirs.
  PRAMANA  the classical epistemology labels nabaos uses: what KIND of support
           a claim would need. We ported the labels and dropped their
           validators, which were substring tests.

Trust levels are deliberately absent until v1.1. A trust level is a calibrated
number; shipping one before the calibration exists would be the overclaim this
project exists to catch.
"""

TYPES = {
    "Fabricated Tool Call": "asserts a tool ran that never appears in the trace",
    "Count Mismatch": "a stated number contradicts what the trace returned",
    "Fact Mismatch": "a stated fact contradicts the content of a tool result",
    "Inference-as-Fact": "a plausible deduction stated as a direct observation",
    "False Absence": "claims nothing exists where the trace shows results",
    "Source Fabrication": "attributes content to a source not present in the trace",
}

PRAMANA = {
    "pratyaksha": "direct observation - a tool result shows it",
    "anumana": "inference from what the trace shows",
    "upamana": "comparison with something else observed",
    "shabda": "testimony - cited from a source in the trace",
    "anupalabdhi": "absence - established by a search that returned nothing",
    "ungrounded": "nothing in the trace bears on it",
}

VERDICTS = ("supported", "unsupported", "uncheckable")

_TYPE_LOOKUP = {k.lower(): k for k in TYPES}


def normalize_type(value):
    """Model output -> a canonical type name, or None if it is not one of ours."""
    return _TYPE_LOOKUP.get(str(value).strip().lower())


def valid(verdict):
    """Is one scorer verdict record well-formed enough to log?"""
    return (isinstance(verdict, dict)
            and isinstance(verdict.get("claim"), str) and verdict["claim"].strip()
            and normalize_type(verdict.get("type")) is not None
            and verdict.get("pramana") in PRAMANA
            and verdict.get("verdict") in VERDICTS)
