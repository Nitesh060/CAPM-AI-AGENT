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

Usage:
    python tools/score_analyzer.py --input results.json
    cat results.json | python tools/score_analyzer.py --stdin
"""

import argparse
import json
import sys
from collections import defaultdict

STRONG_THRESHOLD = 75.0
WEAK_THRESHOLD = 60.0


def _pct(correct, total):
    if total == 0:
        return 0.0
    return round((correct / total) * 100, 1)


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

    data = json.loads(raw)
    attempts = data.get("attempts", [])

    if not attempts:
        print(json.dumps({"error": "No attempts provided."}, indent=2))
        sys.exit(1)

    result = analyze(attempts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
