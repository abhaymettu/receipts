#!/usr/bin/env python3
"""Extract decision points from Claude Code session logs."""
import json, sys, pathlib, re

DECISION_PATTERNS = [
    (r"(?:first|before|instead|prioritize|start with|let me start)", "Priority ordering"),
    (r"(?:i'?ll (?:interpret|read|take)|sounds like|i think you mean|reading this as)", "Interpretation"),
    (r"(?:i'?ll use|going with|choosing|approach|via|instead of)", "Method choice"),
    (r"(?:now|later|wait|hold off|after|first let me|before i)", "Timing"),
    (r"(?:just the|only the|all of|everything|keep it|limit to)", "Scope calibration"),
    (r"(?:i'?ll report|let me tell|i should mention|fyi|heads up|note:)", "Communication"),
]

def extract_decisions(session_path):
    decisions = []
    lines = pathlib.Path(session_path).read_text().strip().split('\n')
    for i, line in enumerate(lines):
        try:
            turn = json.loads(line)
        except json.JSONDecodeError:
            continue
        if turn.get('type') != 'assistant':
            continue
        content = turn.get('message', {}).get('content', '')
        if isinstance(content, list):
            content = ' '.join(c.get('text', '') for c in content if isinstance(c, dict))
        for pattern, dtype in DECISION_PATTERNS:
            if re.search(pattern, content, re.I):
                sentences = re.split(r'[.!?\n]', content)
                for sent in sentences:
                    if re.search(pattern, sent, re.I) and len(sent.strip()) > 20:
                        decisions.append({
                            'session_id': pathlib.Path(session_path).stem,
                            'turn_index': i,
                            'decision_point': sent.strip()[:200],
                            'decision_type': dtype,
                            'context_before': '',
                            'choice_made': sent.strip()[:200],
                            'better_choice': None,
                            'error_type': None,
                            'label': None,
                            'adjudicated': ''
                        })
                        break
                break
    return decisions

if __name__ == '__main__':
    sessions_dir = pathlib.Path.home() / '.claude' / 'projects'
    if not sessions_dir.exists():
        sessions_dir = pathlib.Path.home() / 'Library' / 'Application Support' / 'Claude' / 'projects'
    session_ids = [
        'f9592926-8d2d-4ec8-9c3b-0e18563f9840',
        '530c32a3-9fd8-44ed-8638-873ce633c6e2',
        '52cd0d82-5d3b-40f5-9b3f-b0a10aa7f76d',
        '734deff3-1f37-4d5c-a928-81340fc8475e',
        '5ce0755a-4192-401b-a75f-4bbdc246cf61',
    ]
    all_decisions = []
    for sid in session_ids:
        matches = list(sessions_dir.rglob(f'{sid}.jsonl'))
        if matches:
            decs = extract_decisions(matches[0])
            all_decisions.extend(decs)
            print(f'{sid}: {len(decs)} decision points')
        else:
            print(f'{sid}: not found')
    all_decisions.insert(0, {
        'session_id': 'projectm-main-agent',
        'turn_index': 0,
        'decision_point': 'How to respond to prepone them / start more herdr sessions',
        'decision_type': 'Interpretation + Priority ordering',
        'context_before': 'User had just complained about browser cap, said we shouldnt need the cloud browser, asked about direct herdr access',
        'choice_made': 'Built consolidated paste block for tonight three workstreams',
        'better_choice': 'Recognized user wanted to build the browser-free bridge first',
        'error_type': 'Missed signal + Wrong default',
        'label': 'suboptimal',
        'adjudicated': 'User immediately preceding messages were explicit signals that his interest was eliminating the browser dependency.'
    })
    output = pathlib.Path('decisions.json')
    output.write_text(json.dumps(all_decisions, indent=2) + '\n')
    print(f'Total: {len(all_decisions)} decision points -> {output}')
