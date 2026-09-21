"""Shared utilities for CAPM AI Study Agent tools.

Provides question bank loading/filtering and progress data I/O used by
quiz_engine.py, mock_exam.py, score_analyzer.py, study_plan.py,
progress_tracker.py, selector.py and session.py.

Set the CAPM_DATA_DIR environment variable to redirect all learner data
(progress + sessions) to another directory, e.g. for tests.
"""

import json
import os
import random
import re
from pathlib import Path

import taxonomy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTION_BANK_DIR = PROJECT_ROOT / "question_bank"
DATA_DIR = PROJECT_ROOT / "data"
PROGRESS_FILE = DATA_DIR / "student_progress.json"
SESSIONS_DIR = DATA_DIR / "sessions"
DATA_DIR_ENV = "CAPM_DATA_DIR"

PROGRESS_SCHEMA_VERSION = 2

# Kept for backward compatibility; derived from the taxonomy (PMI published weights).
DOMAIN_FILES = {d.lower(): taxonomy.domain_file(d) for d in taxonomy.practice_domains()}
DOMAIN_FILES["business-analysis"] = DOMAIN_FILES["business analysis"]
DOMAIN_EXAM_WEIGHTS = {d.lower(): w for d, w in taxonomy.official_weights().items()}


class ProgressError(Exception):
    """Learner progress data could not be read safely."""


# --- untrusted-input limits ------------------------------------------------------
# Text that reaches these tools may originate from the student or from pasted
# documents. It is treated strictly as data: bounded, stripped of invisible/control
# characters, and never interpreted (there is no shell, eval or exec in tools/).

MAX_QUESTIONS = 1000        # per quiz/mock request
MAX_INPUT_CHARS = 1_000_000  # per JSON input read from a file or stdin
MAX_NOTE_CHARS = 500         # free-text session notes
MAX_QUERY_CHARS = 100        # topic / domain filters
MAX_WEEKS = 104              # study-plan limits
MAX_HOURS_PER_WEEK = 168
REVEAL_ENV = "CAPM_ALLOW_REVEAL_ANSWERS"  # developer-only opt-in for answer-key output

# ASCII/C1 control characters (keeps \t and \n), zero-width, bidi-override and BOM characters.
_UNSAFE_CHARS = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤⁦-⁩﻿]"
)


def has_unsafe_chars(value):
    return bool(_UNSAFE_CHARS.search(str(value)))


def clean_text(value, max_len=200):
    """Strip control/zero-width/bidi characters and cap the length."""
    return _UNSAFE_CHARS.sub("", str(value))[:max_len]


def shown(value, max_len=60):
    """Short, single-line, printable form of untrusted text for use in messages."""
    text = " ".join(clean_text(value, max_len + 1).split())
    return text if len(text) <= max_len else text[:max_len] + "..."


def check_query_text(name, value):
    """Validate a free-text filter (topic/domain). Raises ValueError if unusable."""
    if value is None:
        return
    if len(value) > MAX_QUERY_CHARS or has_unsafe_chars(value):
        raise ValueError(f"--{name} must be at most {MAX_QUERY_CHARS} printable characters.")


def check_question_count(count, name="count"):
    if count <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    if count > MAX_QUESTIONS:
        raise ValueError(f"{name} must be at most {MAX_QUESTIONS}.")


def reveal_allowed():
    """Answer-key output (--reveal-answers) is a developer opt-in, never part of tutoring."""
    return os.environ.get(REVEAL_ENV) == "1"


def reject_protected_path(path):
    """Refuse to read session files or the question bank through a generic --input option.

    Paths are resolved first, so symlinks and ../ tricks that end up inside a protected
    directory are refused too.
    """
    resolved = Path(path).expanduser().resolve()
    for protected in (get_sessions_dir().resolve(), QUESTION_BANK_DIR.resolve()):
        if resolved == protected or protected in resolved.parents:
            raise ValueError("That path is not readable through this tool.")


def read_text_limited(source, max_chars=MAX_INPUT_CHARS):
    """Read at most max_chars from a file path or file-like object.

    Raises ValueError with a generic message for unreadable, non-text, oversized or
    protected input, so callers never surface a traceback or file contents.
    """
    if isinstance(source, (str, Path)):
        reject_protected_path(source)
    try:
        if isinstance(source, (str, Path)):
            with open(source, encoding="utf-8") as f:
                data = f.read(max_chars + 1)
        else:
            data = source.read(max_chars + 1)
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"Could not read input as UTF-8 text ({type(e).__name__}).") from e
    if len(data) > max_chars:
        raise ValueError(f"Input is larger than {max_chars} characters.")
    return data


# --- data locations ----------------------------------------------------------

def get_progress_file():
    env = os.environ.get(DATA_DIR_ENV)
    if env:
        return Path(env) / "student_progress.json"
    return PROGRESS_FILE


def get_sessions_dir():
    env = os.environ.get(DATA_DIR_ENV)
    if env:
        return Path(env) / "sessions"
    return SESSIONS_DIR


def _lockdown_dir(directory):
    """Create `directory` (and any missing parents) then ensure every level
    up to the data root is owner-only (0700).

    Path.mkdir(mode=...) only applies the given mode to the deepest directory
    it creates, not to intermediate parents it creates along the way (those
    get a permissive default masked only by umask) — so each level is
    chmod'd explicitly here, bounded to the data root and never touching
    anything above it (e.g. the project directory itself).
    """
    directory.mkdir(parents=True, exist_ok=True)
    root = Path(os.environ.get(DATA_DIR_ENV) or DATA_DIR).resolve()
    node = directory.resolve()
    while True:
        os.chmod(node, 0o700)
        if node == root or node == node.parent:
            break
        node = node.parent


def write_json_atomic(path, data):
    """Write JSON to a temp file in the same directory, then atomically replace."""
    path = Path(path)
    _lockdown_dir(path.parent)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)  # learner data and answer keys: owner-only
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


# --- question bank -----------------------------------------------------------

def _normalize_question(q):
    """Copy of the question with domain/topic mapped to canonical taxonomy names."""
    q = dict(q)
    domain = taxonomy.canonical_domain(q.get("domain"))
    if domain:
        q["domain"] = domain
    topic = taxonomy.canonical_topic(q.get("topic"))
    if topic:
        q["topic"] = topic
    return q


def _sanitize(value):
    """Recursively strip control/zero-width/bidi characters from every string in a bank entry."""
    if isinstance(value, str):
        return clean_text(value, 10_000)
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    return value


def _read_bank_file(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize_question(_sanitize(q)) for q in data.get("questions", [])]


def load_all_questions():
    """Load every question from every question bank file."""
    questions = []
    for path in sorted(QUESTION_BANK_DIR.glob("*.json")):
        questions.extend(_read_bank_file(path))
    return questions


def load_domain_questions(domain):
    """Load questions for a single domain by name or alias (case-insensitive)."""
    canonical = taxonomy.canonical_domain(domain)
    filename = taxonomy.domain_file(canonical) if canonical else None
    if not filename:
        return []
    path = QUESTION_BANK_DIR / filename
    if not path.exists():
        return []
    return _read_bank_file(path)


def filter_questions(questions, topic=None, domain=None, difficulty=None):
    """Filter a list of question dicts by optional topic/domain/difficulty.

    Domain accepts names/aliases in any case ("business-analysis" works).
    Topic is resolved in tiers, first tier with results wins:
      1. exact topic name or alias   ("critical path" -> Schedule Management)
      2. a domain name/alias         ("agile" -> the Agile domain)
      3. topic/alias substring       ("stakeholder" -> Stakeholder Management + Engagement)
      4. raw topic substring         (legacy behaviour)
      5. concept_tested / question text substring
    """
    result = list(questions)
    if domain:
        canonical = taxonomy.canonical_domain(domain)
        wanted = canonical or domain.strip().lower()
        result = [q for q in result if q.get("domain", "").strip().lower() == wanted.lower()]
    if difficulty:
        diff = difficulty.strip().lower()
        result = [q for q in result if q.get("difficulty", "").strip().lower() == diff]
    if topic:
        result = _filter_by_topic(result, topic)
    return result


def _filter_by_topic(questions, topic):
    t = topic.strip().lower()

    exact = taxonomy.canonical_topic(topic)
    if exact:
        hits = [q for q in questions if q.get("topic") == exact]
        if hits:
            return hits

    dom = taxonomy.canonical_domain(topic)
    if dom:
        hits = [q for q in questions if q.get("domain") == dom]
        if hits:
            return hits

    names = set(taxonomy.search_topics(topic))
    if names:
        hits = [q for q in questions if q.get("topic") in names]
        if hits:
            return hits

    hits = [q for q in questions if t in q.get("topic", "").strip().lower()]
    if hits:
        return hits

    return [
        q for q in questions
        if t in q.get("concept_tested", "").lower() or t in q.get("question", "").lower()
    ]


def randomize_options(question, rng=None):
    """Return a copy of the question with options shuffled and correct_answer
    letter remapped to match the new order.
    """
    rng = rng or random
    letters = list(question["options"].keys())
    values = list(question["options"].values())
    correct_value = question["options"][question["correct_answer"]]

    paired = list(zip(letters, values))
    rng.shuffle(paired)

    new_options = {}
    new_correct_letter = None
    new_why_wrong = {}
    old_why_wrong = question.get("why_others_are_wrong", {})
    # map old letter -> value -> new letter, to carry explanations along
    old_letter_by_value = {v: k for k, v in question["options"].items()}

    for new_letter, (_, value) in zip(letters, paired):
        new_options[new_letter] = value
        if value == correct_value:
            new_correct_letter = new_letter
        else:
            old_letter = old_letter_by_value[value]
            if old_letter in old_why_wrong:
                new_why_wrong[new_letter] = old_why_wrong[old_letter]

    new_question = dict(question)
    new_question["options"] = new_options
    new_question["correct_answer"] = new_correct_letter
    new_question["why_others_are_wrong"] = new_why_wrong
    return new_question


def strip_answers(question):
    """Return a question dict with answer-revealing fields removed,
    safe to show a student before they respond.
    """
    safe_keys = ("id", "domain", "topic", "difficulty", "type", "question", "options")
    return {k: question[k] for k in safe_keys if k in question}


# --- progress ----------------------------------------------------------------

def new_progress():
    return {"schema_version": PROGRESS_SCHEMA_VERSION, "sessions": [], "attempts": []}


def upgrade_progress(data):
    """Upgrade a v1 progress dict ({"sessions": [...]}) to v2 in memory."""
    if not isinstance(data, dict):
        raise ProgressError("Progress file must contain a JSON object.")
    upgraded = {"schema_version": PROGRESS_SCHEMA_VERSION}
    upgraded.update({k: v for k, v in data.items() if k != "schema_version"})
    upgraded.setdefault("sessions", [])
    upgraded.setdefault("attempts", [])
    return upgraded


def load_progress():
    """Load student progress (always returned in v2 shape).

    A missing file yields an empty history. A corrupt file raises ProgressError
    rather than being silently replaced.
    """
    path = get_progress_file()
    if not path.exists():
        return new_progress()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ProgressError(
            f"{path} is not valid JSON ({e}). Fix or move the file; it was not overwritten."
        ) from e
    return upgrade_progress(data)


def save_progress(data):
    write_json_atomic(get_progress_file(), upgrade_progress(data))
