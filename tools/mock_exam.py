#!/usr/bin/env python3
"""Mock Exam Generator for the CAPM AI Study Agent.

Builds a practice mock exam from the AI-generated question bank. Domain counts
follow the domain weights PMI publishes in its CAPM Examination Content Outline
(2023 Exam Update; see config/taxonomy.json for source and retrieval date):
    Project Management Fundamentals and Core Concepts   36%
    Predictive, Plan-Based Methodologies                17%
    Agile Frameworks/Methodologies                      20%
    Business Analysis Frameworks                        27%

Those weights are PMI's; the questions are ours (AI-generated). This is NOT an
official PMI exam and does not reproduce the real exam's content or difficulty.

Questions are never silently repeated. If the requested size exceeds the unique
questions available, the exam is capped at the maximum unique questions and a
warning is returned, unless --allow-repeats is passed explicitly. When a domain
runs out of unique questions its shortfall is redistributed to the other
domains as close to the official weights as possible, and any deviation is
reported.

--reveal-answers prints the answer key and is for developers and scripts only,
never for tutoring (see SECURITY.md).

Usage:
    python tools/mock_exam.py --questions 20
    python tools/mock_exam.py --questions 150
    python tools/mock_exam.py --questions 60 --seed 42
    python tools/mock_exam.py --questions 150 --allow-repeats
"""

import argparse
import json
import math
import random
import sys

import taxonomy
from common import check_question_count, load_domain_questions, randomize_options, reveal_allowed, strip_answers


def _largest_remainder(total, weights):
    """Split `total` across domains proportionally to `weights` (integers, sum == total)."""
    raw = {d: round(total * w, 9) for d, w in weights.items()}
    counts = {d: int(v) for d, v in raw.items()}
    order = list(weights)
    remainder = total - sum(counts.values())
    by_fraction = sorted(order, key=lambda d: (-(raw[d] - counts[d]), order.index(d)))
    for d in by_fraction[:remainder]:
        counts[d] += 1
    return counts


def _allocate_with_capacity(total, weights, capacities):
    """Weight-proportional allocation where each domain is capped at its capacity.

    Returns (ideal, actual). `actual` never exceeds capacities; any shortfall is
    handed, one question at a time, to the domain furthest below its ideal share.
    """
    total = min(total, sum(capacities.values()))
    ideal = _largest_remainder(total, weights)
    actual = {d: min(ideal[d], capacities[d]) for d in weights}
    order = list(weights)
    deficit = total - sum(actual.values())
    while deficit > 0:
        open_domains = [d for d in order if actual[d] < capacities[d]]
        pick = max(open_domains, key=lambda d: (weights[d] * total - actual[d], -order.index(d)))
        actual[pick] += 1
        deficit -= 1
    return ideal, actual


def build_mock_exam(question_count, seed=None, allow_repeats=False):
    rng = random.Random(seed)
    weights = taxonomy.official_weights()
    pools = {d: load_domain_questions(d) for d in weights}
    warnings = []

    if allow_repeats:
        target = _largest_remainder(question_count, weights)
        counts = dict(target)
    else:
        capacities = {d: len(p) for d, p in pools.items()}
        unique_total = sum(capacities.values())
        if question_count > unique_total:
            warnings.append(
                f"Requested {question_count} questions but only {unique_total} unique questions exist in the "
                f"bank; returning {unique_total} unique questions. Pass --allow-repeats to force repeated questions."
            )
        target, counts = _allocate_with_capacity(question_count, weights, capacities)
        if counts != target:
            gaps = ", ".join(f"{d} {counts[d]} vs {target[d]}" for d in weights if counts[d] != target[d])
            warnings.append(
                "The domain mix deviates from the official weights because some domains have too few unique "
                f"questions ({gaps})."
            )

    selected = []
    for domain, needed in counts.items():
        pool = list(pools[domain])
        if needed == 0:
            continue
        if not pool:
            warnings.append(f"Domain '{domain}' has no questions in the bank.")
            counts[domain] = 0
            continue
        chosen = []
        while len(chosen) < needed:
            rng.shuffle(pool)
            chosen.extend(pool[: needed - len(chosen)])
        if needed > len(pool):
            warnings.append(
                f"Domain '{domain}' needed {needed} questions but only {len(pool)} unique questions exist; "
                "some questions were repeated (--allow-repeats)."
            )
        selected.extend(chosen)

    rng.shuffle(selected)
    selected = [randomize_options(q, rng=rng) for q in selected]

    return {
        "exam_type": "CAPM Practice Mock Exam (AI-generated)",
        "requested_questions": question_count,
        "actual_questions": len(selected),
        "unique_questions": len({q["id"] for q in selected}),
        "domain_distribution_target": target if allow_repeats else _largest_remainder(len(selected), weights),
        "domain_distribution_actual": counts,
        "official_domain_weights": weights,
        "distribution_basis": (
            "Domain counts follow PMI's published CAPM domain weights (2023 Exam Update) applied to "
            "AI-generated practice questions. This is not PMI's question distribution."
        ),
        "suggested_time_minutes": math.ceil(len(selected) * taxonomy.exam_facts()["duration_minutes"] / taxonomy.exam_facts()["total_questions"]),
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
    parser.add_argument("--allow-repeats", action="store_true", help="Allow repeated questions if the bank has fewer unique questions than requested")
    parser.add_argument("--no-repeats", action="store_true", help="Deprecated no-op: repeats are off by default")
    parser.add_argument("--reveal-answers", action="store_true", help="Developer-only: print the answer key. Refused unless a developer opt-in is set; never used for tutoring")
    args = parser.parse_args()

    if args.reveal_answers and not reveal_allowed():
        print(json.dumps({
            "error": "--reveal-answers is disabled: it prints the answer key and is not available for tutoring. See SECURITY.md.",
        }, indent=2))
        sys.exit(1)

    try:
        check_question_count(args.questions, "--questions")
    except ValueError as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)
    if args.allow_repeats and args.no_repeats:
        print(json.dumps({"error": "--allow-repeats and --no-repeats are mutually exclusive"}, indent=2))
        sys.exit(1)

    exam = build_mock_exam(args.questions, seed=args.seed, allow_repeats=args.allow_repeats)

    if not args.reveal_answers:
        exam["questions"] = [strip_answers(q) for q in exam["questions"]]

    print(json.dumps(exam, indent=2))


if __name__ == "__main__":
    main()
