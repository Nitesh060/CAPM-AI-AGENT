#!/usr/bin/env python3
"""Question bank validator for the CAPM AI Study Agent.

Checks every question_bank/*.json file against the schema in the README and the
taxonomy in config/taxonomy.json. Exits non-zero if any error is found;
warnings (e.g. a skewed answer-key distribution) do not fail the run.

Bank text is shown to the tutor as data, so it is also checked structurally:
no control, zero-width or bidi-override characters (hidden text) and sane length limits.

Usage:
    python tools/validate_bank.py
"""

import collections
import json
import sys

import taxonomy
from common import QUESTION_BANK_DIR, has_unsafe_chars

REQUIRED_FIELDS = (
    "id", "domain", "topic", "difficulty", "type", "question", "options",
    "correct_answer", "explanation", "why_others_are_wrong", "concept_tested", "source",
)
DIFFICULTIES = {"easy", "medium", "hard"}
QUESTION_TYPES = {"knowledge", "scenario"}
KEY_SKEW_MAX_SHARE = 0.40
KEY_SKEW_MIN_SAMPLE = 20
# Generous limits (the current bank's longest fields are under 300 characters).
LENGTH_LIMITS = {"question": 2000, "option": 600, "explanation": 2500, "why_others_are_wrong": 1000, "concept_tested": 200}


def validate_bank(bank_dir=None):
    """Return (errors, warnings, question_count)."""
    bank_dir = bank_dir or QUESTION_BANK_DIR
    errors, warnings = [], []
    ids = collections.Counter()
    answer_keys = collections.Counter()
    count = 0

    files = sorted(bank_dir.glob("*.json"))
    if not files:
        errors.append(f"No question bank files found in {bank_dir}.")

    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: invalid JSON ({e}).")
            continue

        meta = data.get("metadata", {})
        if meta.get("source_type") != "ai_generated":
            errors.append(f"{path.name}: metadata.source_type must be 'ai_generated' (got {meta.get('source_type')!r}).")
        file_domain = taxonomy.canonical_domain(meta.get("domain"))
        if not file_domain:
            errors.append(f"{path.name}: metadata.domain {meta.get('domain')!r} is not a known domain.")
        elif taxonomy.domain_file(file_domain) != path.name:
            errors.append(f"{path.name}: taxonomy expects domain {file_domain!r} in {taxonomy.domain_file(file_domain)}.")

        for q in data.get("questions", []):
            count += 1
            qid = q.get("id", f"<no id in {path.name} #{count}>")
            ids[qid] += 1

            missing = [k for k in REQUIRED_FIELDS if k not in q]
            if missing:
                errors.append(f"{qid}: missing fields {missing}.")
                continue

            # Bank text is shown to the tutor as data: no hidden characters, bounded length.
            texts = [("question", q["question"], "question"), ("explanation", q["explanation"], "explanation"),
                     ("concept_tested", q["concept_tested"], "concept_tested")]
            texts += [(f"option {k}", v, "option") for k, v in q["options"].items()]
            texts += [(f"why_others_are_wrong {k}", v, "why_others_are_wrong") for k, v in q["why_others_are_wrong"].items()]
            for label, text, limit_key in texts:
                if not isinstance(text, str):
                    errors.append(f"{qid}: {label} must be text.")
                    continue
                if has_unsafe_chars(text):
                    errors.append(f"{qid}: {label} contains control, zero-width or bidi-override characters.")
                if len(text) > LENGTH_LIMITS[limit_key]:
                    errors.append(f"{qid}: {label} is longer than {LENGTH_LIMITS[limit_key]} characters.")

            options = q["options"]
            if set(options) != {"A", "B", "C", "D"}:
                errors.append(f"{qid}: options must be exactly A-D (got {sorted(options)}).")
            if len(set(options.values())) != len(options):
                errors.append(f"{qid}: duplicate option text.")
            if q["correct_answer"] not in options:
                errors.append(f"{qid}: correct_answer {q['correct_answer']!r} is not an option key.")
            else:
                answer_keys[q["correct_answer"]] += 1
                wrong = set(options) - {q["correct_answer"]}
                if set(q["why_others_are_wrong"]) != wrong:
                    errors.append(f"{qid}: why_others_are_wrong keys {sorted(q['why_others_are_wrong'])} != wrong options {sorted(wrong)}.")

            if q["difficulty"] not in DIFFICULTIES:
                errors.append(f"{qid}: difficulty {q['difficulty']!r} not in {sorted(DIFFICULTIES)}.")
            if q["type"] not in QUESTION_TYPES:
                errors.append(f"{qid}: type {q['type']!r} not in {sorted(QUESTION_TYPES)}.")

            domain = taxonomy.canonical_domain(q["domain"])
            topic = taxonomy.canonical_topic(q["topic"])
            if not domain:
                errors.append(f"{qid}: unknown domain {q['domain']!r}.")
            elif file_domain and domain != file_domain:
                errors.append(f"{qid}: domain {domain!r} does not match its file's domain {file_domain!r}.")
            if not topic:
                errors.append(f"{qid}: topic {q['topic']!r} is not in config/taxonomy.json.")
            elif domain and taxonomy.topic_domain(topic) != domain:
                errors.append(f"{qid}: topic {topic!r} belongs to {taxonomy.topic_domain(topic)!r}, not {domain!r}.")

    for qid, n in ids.items():
        if n > 1:
            errors.append(f"Duplicate id {qid} ({n} times).")

    total_keys = sum(answer_keys.values())
    if total_keys >= KEY_SKEW_MIN_SAMPLE:
        top_letter, top_n = answer_keys.most_common(1)[0]
        if top_n / total_keys > KEY_SKEW_MAX_SHARE:
            dist = ", ".join(f"{k}={answer_keys[k]}" for k in "ABCD")
            warnings.append(
                f"Answer-key distribution is skewed ({dist}); option shuffling hides this, but --no-shuffle exposes it."
            )

    return errors, warnings, count


def main():
    errors, warnings, count = validate_bank()
    print(json.dumps({
        "ok": not errors,
        "questions_checked": count,
        "errors": errors,
        "warnings": warnings,
    }, indent=2))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
