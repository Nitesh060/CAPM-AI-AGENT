"""Adaptive question selector for the CAPM AI Study Agent.

Given a candidate pool (already filtered by topic/domain/difficulty) and the
learner's progress history, pick `count` questions by weighted sampling without
replacement. Each question's weight is

    topic_weight  = max(1 - estimated_mastery(topic), 0.15)     weaker topics first
  x novelty       unseen 1.5 | last answer wrong: 2.0 (0.5 if in the last 3 attempts)
                  | last answer right: 0.3 (0.1 if within the recent window)
  x difficulty_fit  1.0 at the topic's target difficulty, 0.5 one step away, 0.2 two steps

Nothing is ever excluded outright, so small pools never run dry. Selection is
deterministic for a given random.Random seed.
"""

from progress_tracker import DIFFICULTY_ORDER, MASTERY_PRIOR, WEIGHT_FLOOR, topic_mastery, topic_target_difficulty

RECENT_WINDOW = 20
DIFFICULTY_FIT = (1.0, 0.5, 0.2)


def question_history(progress):
    """{question_id: {"last_correct": bool, "age": attempts since last seen}} from v2 attempts."""
    attempts = progress.get("attempts", [])
    total = len(attempts)
    history = {}
    for index, a in enumerate(attempts):
        qid = a.get("question_id")
        if qid:
            history[qid] = {"last_correct": bool(a["correct"]), "age": total - 1 - index}
    return history


def _difficulty_index(name):
    name = (name or "medium").lower()
    return DIFFICULTY_ORDER.index(name) if name in DIFFICULTY_ORDER else 1


def question_weight(q, mastery, targets, history):
    estimate = mastery.get(q["topic"], {}).get("estimate", MASTERY_PRIOR)
    topic_weight = max(1 - estimate, WEIGHT_FLOOR)

    seen = history.get(q["id"])
    if not seen:
        novelty = 1.5
    elif seen["last_correct"]:
        novelty = 0.1 if seen["age"] < RECENT_WINDOW else 0.3
    else:
        novelty = 0.5 if seen["age"] < 3 else 2.0

    target = targets.get(q["topic"], "medium")
    distance = abs(_difficulty_index(q.get("difficulty")) - _difficulty_index(target))
    fit = DIFFICULTY_FIT[min(distance, len(DIFFICULTY_FIT) - 1)]

    return topic_weight * novelty * fit


def select_questions(pool, count, progress, rng):
    """Return (selected_questions, meta). `meta` explains what drove the selection."""
    mastery = topic_mastery(progress)
    targets = topic_target_difficulty(progress)
    history = question_history(progress)

    keyed = []
    for q in pool:
        weight = max(question_weight(q, mastery, targets, history), 1e-9)
        # Efraimidis-Spirakis: larger key = more likely to be picked, without replacement.
        keyed.append((rng.random() ** (1.0 / weight), q["id"], q))
    keyed.sort(key=lambda item: (-item[0], item[1]))
    selected = [q for _, _, q in keyed[:count]]

    meta = {
        "mode": "adaptive" if mastery else "cold_start",
        "pool_size": len(pool),
        "topics_selected": sorted({q["topic"] for q in selected}),
        "target_difficulty": {t: targets[t] for t in sorted({q["topic"] for q in selected}) if t in targets},
    }
    return selected, meta
