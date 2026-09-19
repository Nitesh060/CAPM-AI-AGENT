#!/usr/bin/env python3
"""Mock Exam Generator for the CAPM AI Study Agent.

Generates a full-length practice/mock exam with questions distributed
across the three official CAPM exam domains, approximating PMI's published
weighting:
    Predictive, Plan-Based Projects  ~50%
    Agile/Adaptive Projects          ~25%
    Business Acumen                  ~25%

Usage:
    python tools/mock_exam.py --questions 20
    python tools/mock_exam.py --questions 150
    python tools/mock_exam.py --questions 60 --seed 42

IMPORTANT: This is an original, AI-generated PRACTICE exam. It is NOT an
official PMI exam and does not claim to reproduce the real CAPM exam
question-for-question. Question bank size is limited; if the requested
count exceeds available unique questions in a domain, questions may repeat
(flagged in the output) unless --no-repeats is set, in which case the exam
is capped at the number of unique questions available.
"""

import argparse
import json
import random
import sys

from common import DOMAIN_EXAM_WEIGHTS, load_domain_questions, randomize_options, strip_answers


def build_mock_exam(question_count, seed=None, allow_repeats=True):
    rng = random.Random(seed)

    domain_counts = {}
    running_total = 0
    domains = list(DOMAIN_EXAM_WEIGHTS.keys())
    for i, domain in enumerate(domains):
        if i == len(domains) - 1:
            domain_counts[domain] = question_count - running_total
        else:
            n = round(question_count * DOMAIN_EXAM_WEIGHTS[domain])
            domain_counts[domain] = n
            running_total += n

    selected = []
    warnings = []

    for domain, needed in domain_counts.items():
        pool = load_domain_questions(domain)
        rng.shuffle(pool)

        if len(pool) >= needed:
            chosen = pool[:needed]
        elif allow_repeats and pool:
            chosen = []
            while len(chosen) < needed:
                remaining = needed - len(chosen)
                rng.shuffle(pool)
                chosen.extend(pool[:remaining])
            warnings.append(
                f"Domain '{domain}' needed {needed} questions but only {len(pool)} unique "
                f"questions exist in the bank; some questions were repeated."
            )
        else:
            chosen = pool
            warnings.append(
                f"Domain '{domain}' needed {needed} questions but only {len(pool)} unique "
                f"questions exist and repeats are disabled; exam is short by {needed - len(pool)}."
            )

        selected.extend(chosen)

    rng.shuffle(selected)
    selected = [randomize_options(q, rng=rng) for q in selected]

    return {
        "exam_type": "CAPM Practice Mock Exam (AI-generated)",
        "requested_questions": question_count,
        "actual_questions": len(selected),
        "domain_distribution_target": domain_counts,
        "warnings": warnings,
        "disclaimer": (
            "This is an original, AI-generated practice exam for study purposes only. "
            "It is not produced or endorsed by PMI and does not guarantee reproduction "
            "of the official CAPM exam content, difficulty, or passing outcome."
        ),
        "questions": selected,
    }


def main():
    parser = argparse.ArgumentParser(description="CAPM Mock Exam Generator")
    parser.add_argument("--questions", type=int, default=20, help="Total number of questions (e.g. 20, 60, 150)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--no-repeats", action="store_true", help="Do not repeat questions even if bank is smaller than requested count")
    parser.add_argument("--reveal-answers", action="store_true", help="Include correct answers/explanations (default: hidden, student-safe)")
    args = parser.parse_args()

    if args.questions <= 0:
        print(json.dumps({"error": "--questions must be a positive integer"}, indent=2))
        sys.exit(1)

    exam = build_mock_exam(args.questions, seed=args.seed, allow_repeats=not args.no_repeats)

    if not args.reveal_answers:
        exam["questions"] = [strip_answers(q) for q in exam["questions"]]

    print(json.dumps(exam, indent=2))


if __name__ == "__main__":
    main()
