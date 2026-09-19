#!/usr/bin/env python3
"""Quiz Engine for the CAPM AI Study Agent.

Selects questions from the question bank based on topic/domain/difficulty
filters, optionally randomizes answer options, and outputs structured JSON
that an AI agent (or another tool) can present to the student one question
at a time.

Usage:
    python tools/quiz_engine.py --topic agile --count 10
    python tools/quiz_engine.py --topic "schedule management" --count 10
    python tools/quiz_engine.py --difficulty hard --count 20
    python tools/quiz_engine.py --domain predictive --count 10
    python tools/quiz_engine.py --domain agile --count 5 --no-shuffle
    python tools/quiz_engine.py --count 10 --reveal-answers
"""

import argparse
import json
import random
import sys

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

    return {
        "quiz_size": len(selected),
        "requested_count": count,
        "filters": {"topic": topic, "domain": domain, "difficulty": difficulty},
        "questions": selected,
    }


def main():
    parser = argparse.ArgumentParser(description="CAPM Quiz Engine")
    parser.add_argument("--topic", type=str, default=None, help="Filter by topic (partial match, e.g. 'schedule management')")
    parser.add_argument("--domain", type=str, default=None, help="Filter by domain: fundamentals, predictive, agile, business analysis")
    parser.add_argument("--difficulty", type=str, default=None, choices=["easy", "medium", "hard"], help="Filter by difficulty")
    parser.add_argument("--count", type=int, default=10, help="Number of questions to select")
    parser.add_argument("--no-shuffle", action="store_true", help="Do not randomize answer option order")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible quizzes")
    parser.add_argument("--reveal-answers", action="store_true", help="Include correct answers/explanations in output (default: hidden, student-safe)")
    args = parser.parse_args()

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
