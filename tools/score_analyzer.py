#!/usr/bin/env python3
"""Score Analyzer for the CAPM AI Study Agent.

Takes a set of quiz/mock-exam attempts and produces a performance breakdown:
overall score, per-domain and per-topic performance, strong/weak topics, and
revision recommendations.

Input format (JSON), via --input <file> or stdin:
{
  "attempts": [
    {"question_id": "AGILE-001", "domain": "Agile", "topic": "Scrum Roles",
     "difficulty": "easy", "correct": true},
    ...
  ]
}

Attempts are validated and normalised first: `correct` must be a real boolean,
domain/topic names are mapped to the canonical taxonomy (so "scrum roles" and
"Scrum Roles" are one topic), and when the question_id exists in the bank its
domain/topic/difficulty are taken from the bank.

Usage:
    python tools/score_analyzer.py --input results.json
    cat results.json | python tools/score_analyzer.py --stdin
"""

import argparse
import json
import sys
from collections import defaultdict

import taxonomy
from common import load_all_questions

STRONG_THRESHOLD = 75.0
WEAK_THRESHOLD = 60.0
DIFFICULTIES = ("easy", "medium", "hard")


class AttemptError(ValueError):
    """The attempts payload is malformed."""


def _pct(correct, total):
    if total == 0:
        return 0.0
    return round((correct / total) * 100, 1)


def normalize_attempts(attempts):
    """Validate and canonicalise attempts. Returns (attempts, warnings).

    Raises AttemptError on malformed input (non-boolean `correct`, unknown
    domain/topic/difficulty for questions that are not in the bank, ...).
    """
    if not isinstance(attempts, list) or not attempts:
        raise AttemptError("'attempts' must be a non-empty list.")

    bank = {q["id"]: q for q in load_all_questions() if "id" in q}
    normalized, warnings = [], []

    for i, a in enumerate(attempts, start=1):
        if not isinstance(a, dict):
            raise AttemptError(f"Attempt #{i} must be a JSON object.")
        if not isinstance(a.get("correct"), bool):
            raise AttemptError(f"Attempt #{i}: 'correct' must be true or false (got {a.get('correct')!r}).")

        qid = a.get("question_id")
        bank_q = bank.get(qid) if qid else None

        if bank_q:
            domain, topic, difficulty = bank_q["domain"], bank_q["topic"], bank_q["difficulty"].lower()
        else:
            domain = taxonomy.canonical_domain(a.get("domain"))
            topic = taxonomy.canonical_topic(a.get("topic"))
            difficulty = str(a.get("difficulty", "")).strip().lower()
            if not domain:
                raise AttemptError(
                    f"Attempt #{i}: unknown domain {a.get('domain')!r}. Valid: {', '.join(taxonomy.practice_domains())}."
                )
            if not topic:
                raise AttemptError(
                    f"Attempt #{i}: unknown topic {a.get('topic')!r}. Run 'python tools/quiz_engine.py --list-topics'."
                )
            if taxonomy.topic_domain(topic) != domain:
                raise AttemptError(
                    f"Attempt #{i}: topic {topic!r} belongs to {taxonomy.topic_domain(topic)!r}, not {domain!r}."
                )
            if difficulty not in DIFFICULTIES:
                raise AttemptError(f"Attempt #{i}: difficulty must be one of {', '.join(DIFFICULTIES)}.")
            warnings.append(f"Attempt #{i}: question_id {qid!r} is not in the bank; accepted as an external question.")

        record = {
            "question_id": qid,
            "domain": domain,
            "topic": topic,
            "difficulty": difficulty,
            "correct": a["correct"],
        }
        for optional in ("chosen", "answered_at"):
            if a.get(optional) is not None:
                record[optional] = a[optional]
        normalized.append(record)

    return normalized, warnings


def analyze(attempts):
    total = len(attempts)
    correct_total = sum(1 for a in attempts if a.get("correct"))
    incorrect_total = total - correct_total

    domain_stats = defaultdict(lambda: {"attempted": 0, "correct": 0})
    topic_stats = defaultdict(lambda: {"attempted": 0, "correct": 0})
    difficulty_stats = defaultdict(lambda: {"attempted": 0, "correct": 0})

    for a in attempts:
        domain = a.get("domain", "Unknown")
        topic = a.get("topic", "Unknown")
        difficulty = a.get("difficulty", "Unknown")
        is_correct = bool(a.get("correct"))

        domain_stats[domain]["attempted"] += 1
        domain_stats[domain]["correct"] += 1 if is_correct else 0

        topic_stats[topic]["attempted"] += 1
        topic_stats[topic]["correct"] += 1 if is_correct else 0

        difficulty_stats[difficulty]["attempted"] += 1
        difficulty_stats[difficulty]["correct"] += 1 if is_correct else 0

    domain_performance = {
        d: {
            "attempted": s["attempted"],
            "correct": s["correct"],
            "percentage": _pct(s["correct"], s["attempted"]),
        }
        for d, s in domain_stats.items()
    }

    topic_performance = {
        t: {
            "attempted": s["attempted"],
            "correct": s["correct"],
            "percentage": _pct(s["correct"], s["attempted"]),
        }
        for t, s in topic_stats.items()
    }

    difficulty_performance = {
        diff: {
            "attempted": s["attempted"],
            "correct": s["correct"],
            "percentage": _pct(s["correct"], s["attempted"]),
        }
        for diff, s in difficulty_stats.items()
    }

    strong_topics = sorted(
        [t for t, s in topic_performance.items() if s["percentage"] >= STRONG_THRESHOLD],
        key=lambda t: -topic_performance[t]["percentage"],
    )
    weak_topics = sorted(
        [t for t, s in topic_performance.items() if s["percentage"] < WEAK_THRESHOLD],
        key=lambda t: topic_performance[t]["percentage"],
    )

    recommended_revision = [
        {
            "topic": t,
            "current_score": topic_performance[t]["percentage"],
            "reason": "Below recommended proficiency threshold ({:.0f}%)".format(WEAK_THRESHOLD),
        }
        for t in weak_topics
    ]

    return {
        "summary": {
            "total_attempted": total,
            "correct": correct_total,
            "incorrect": incorrect_total,
            "percentage": _pct(correct_total, total),
        },
        "domain_performance": domain_performance,
        "topic_performance": topic_performance,
        "difficulty_performance": difficulty_performance,
        "strong_topics": strong_topics,
        "weak_topics": weak_topics,
        "recommended_revision": recommended_revision,
        "disclaimer": (
            "This score reflects performance on practice questions only. "
            "It does not guarantee a passing result on the official PMI CAPM exam."
        ),
    }


def _fail(message):
    print(json.dumps({"error": message}, indent=2))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="CAPM Score Analyzer")
    parser.add_argument("--input", type=str, default=None, help="Path to JSON file with attempts")
    parser.add_argument("--stdin", action="store_true", help="Read attempts JSON from stdin")
    args = parser.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    elif args.input:
        with open(args.input, encoding="utf-8") as f:
            raw = f.read()
    else:
        parser.error("Provide either --input <file> or --stdin")
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _fail(f"Input is not valid JSON: {e}")
    if not isinstance(data, dict):
        _fail("Input must be a JSON object with an 'attempts' list.")

    attempts = data.get("attempts", [])
    if not attempts:
        _fail("No attempts provided.")

    try:
        normalized, warnings = normalize_attempts(attempts)
    except AttemptError as e:
        _fail(str(e))

    result = analyze(normalized)
    if warnings:
        result["warnings"] = warnings
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
