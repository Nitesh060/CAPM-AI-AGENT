"""Shared test helpers. All learner data goes to a temp dir via CAPM_DATA_DIR.

Subprocess runs never inherit the developer answer-key opt-in unless a test asks for it
with reveal=True, so the default matches what the tutor sees.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.dont_write_bytecode = True

ANSWER_KEYS = {"correct_answer", "explanation", "why_others_are_wrong", "concept_tested"}


class TempDataCase(unittest.TestCase):
    """Redirects progress + session storage to a throwaway directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self._old_env = os.environ.get("CAPM_DATA_DIR")
        os.environ["CAPM_DATA_DIR"] = str(self.data_dir)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("CAPM_DATA_DIR", None)
        else:
            os.environ["CAPM_DATA_DIR"] = self._old_env
        self._tmp.cleanup()


def run_cli(script, *args, stdin=None, data_dir=None, reveal=False, env_extra=None, binary_stdin=None):
    """Run a tools/ script (argv list, never a shell). Returns (exit_code, stdout, stderr)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("CAPM_ALLOW_REVEAL_ANSWERS", None)
    if reveal:
        env["CAPM_ALLOW_REVEAL_ANSWERS"] = "1"
    if data_dir is not None:
        env["CAPM_DATA_DIR"] = str(data_dir)
    if env_extra:
        env.update(env_extra)
    if binary_stdin is not None:
        proc = subprocess.run(
            [sys.executable, str(TOOLS / script), *args],
            input=binary_stdin, capture_output=True, env=env, cwd=str(ROOT),
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
    proc = subprocess.run(
        [sys.executable, str(TOOLS / script), *args],
        input=stdin, capture_output=True, text=True, env=env, cwd=str(ROOT),
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_json(script, *args, **kwargs):
    """Run a tools/ script and parse its stdout as JSON. Returns (exit_code, parsed)."""
    code, out, err = run_cli(script, *args, **kwargs)
    try:
        return code, json.loads(out)
    except json.JSONDecodeError:
        raise AssertionError(f"{script} {args} printed non-JSON (exit {code}):\n{out}\n{err}")


def find_keys(obj, forbidden):
    """Set of forbidden dict keys appearing anywhere inside obj."""
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in forbidden:
                found.add(k)
            found |= find_keys(v, forbidden)
    elif isinstance(obj, list):
        for item in obj:
            found |= find_keys(item, forbidden)
    return found


def bank_question(topic, index=0):
    """A canonical bank question for a topic."""
    import common
    matches = [q for q in common.load_all_questions() if q["topic"] == topic]
    return matches[index]


def attempt(question, correct):
    return {
        "question_id": question["id"], "domain": question["domain"], "topic": question["topic"],
        "difficulty": question["difficulty"], "correct": correct,
    }
