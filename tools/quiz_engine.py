#!/usr/bin/env python3
"""Quiz Engine for the CAPM AI Study Agent.

Selects questions from the question bank based on topic/domain/difficulty
filters, optionally randomizes answer options, and outputs structured JSON.

This is the stateless batch tool. For an interactive tutoring flow (grading
kept server-side so answers are never exposed early) use tools/session.py.

Usage:
    python tools/quiz_engine.py --topic agile --count 10
    python tools/quiz_engine.py --topic "critical path" --count 10
    python tools/quiz_engine.py --difficulty hard --count 20
    python tools/quiz_engine.py --domain predictive --count 10
    python tools/quiz_engine.py --domain agile --count 5 --no-shuffle
    python tools/quiz_engine.py --count 10 --reveal-answers
    python tools/quiz_engine.py --list-topics
"""

import argparse
import json
import random
import sys

import taxonomy
from common import filter_questions, load_all_questions, randomize_options, strip_answers


def build_quiz(count, topic=None, domain=None, difficulty=None, shuffle_options=True, seed=None):
    rng = random.Random(seed)

    all_questions = load_all_questions()
    candidates = filter_questions(all_questions, topic=topic, domain=domain, difficulty=difficulty)

    if not candidates:
        return {
            "error": "No questions matched the given filters.",
            "filters": {"topic": topic, "domain": domain, "difficulty": difficulty},
        }

    rng.shuffle(candidates)
    selected = candidates[:count]

    if shuffle_options:
        selected = [randomize_options(q, rng=rng) for q in selected]

    quiz = {
        "quiz_size": len(selected),
        "requested_count": count,
        "filters": {"topic": topic, "domain": domain, "difficulty": difficulty},
        "questions": selected,
    }
    if len(selected) < count:
        quiz["shortfall"] = count - len(selected)
        quiz["warning"] = (
            f"Only {len(selected)} matching question(s) exist; requested {count}. "
            "Questions are not repeated."
        )
    return quiz


def list_topics():
    """Canonical topics grouped by domain, with the number of bank questions each."""
    counts = {}
    for q in load_all_questions():
        counts[q["topic"]] = counts.get(q["topic"], 0) + 1
    return {
        "domains": {
            d: [{"topic": t, "questions": counts.get(t, 0)} for t in taxonomy.topics_for_domain(d)]
            for d in taxonomy.practice_domains()
        },
        "note": "Aliases (e.g. 'critical path', 'evm', 'scrum master') are accepted by --topic.",
    }


def main():
    parser = argparse.ArgumentParser(description="CAPM Quiz Engine")
    parser.add_argument("--topic", type=str, default=None, help="Topic, alias, or domain (e.g. 'critical path', 'schedule management', 'agile')")
    parser.add_argument("--domain", type=str, default=None, help="Filter by domain: fundamentals, predictive, agile, business analysis")
    parser.add_argument("--difficulty", type=str, default=None, choices=["easy", "medium", "hard"], help="Filter by difficulty")
    parser.add_argument("--count", type=int, default=10, help="Number of questions to select")
    parser.add_argument("--no-shuffle", action="store_true", help="Do not randomize answer option order")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible quizzes")
    parser.add_argument("--reveal-answers", action="store_true", help="Include correct answers/explanations in output (default: hidden, student-safe)")
    parser.add_argument("--list-topics", action="store_true", help="List canonical topics per domain and exit")
    args = parser.parse_args()

    if args.list_topics:
        print(json.dumps(list_topics(), indent=2))
        return

    if args.domain and not taxonomy.canonical_domain(args.domain):
        print(json.dumps({
            "error": f"Unknown domain {args.domain!r}.",
            "valid_domains": taxonomy.practice_domains(),
        }, indent=2))
        sys.exit(1)

    quiz = build_quiz(
        count=args.count,
        topic=args.topic,
        domain=args.domain,
        difficulty=args.difficulty,
        shuffle_options=not args.no_shuffle,
        seed=args.seed,
    )

    if "error" in quiz:
        print(json.dumps(quiz, indent=2))
        sys.exit(1)

    if not args.reveal_answers:
        quiz["questions"] = [strip_answers(q) for q in quiz["questions"]]

    print(json.dumps(quiz, indent=2))


if __name__ == "__main__":
    main()
