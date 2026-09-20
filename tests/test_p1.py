"""P1 tests: progress v2, adaptive selector, session engine, CLI backward compatibility."""

import json
import random
import unittest
from collections import Counter

from helpers import ANSWER_KEYS, ROOT, TempDataCase, attempt, bank_question, find_keys, run_cli, run_json

import common
import progress_tracker
import selector
import session
import taxonomy


def record(session_type, attempts, session_id=None):
    return progress_tracker.record_session(session_type, attempts, session_id=session_id)


class TestProgressV2(TempDataCase):
    def test_missing_file_is_empty_v2(self):
        progress = common.load_progress()
        self.assertEqual(progress, {"schema_version": 2, "sessions": [], "attempts": []})

    def test_v1_file_is_upgraded_in_memory_without_data_loss(self):
        v1 = {"sessions": [{"date": "2026-01-01", "type": "quiz", "attempted": 2, "correct": 1, "incorrect": 1,
                            "score_percentage": 50.0, "domain_performance": {}, "topic_performance": {},
                            "weak_topics": [], "strong_topics": []}]}
        (self.data_dir / "student_progress.json").write_text(json.dumps(v1))
        progress = common.load_progress()
        self.assertEqual(progress["schema_version"], 2)
        self.assertEqual(progress["attempts"], [])
        self.assertEqual(progress["sessions"], v1["sessions"])

    def test_record_writes_session_and_attempts(self):
        q = bank_question("Kanban")
        s = record("quiz", [attempt(q, True), attempt(q, False)])
        progress = common.load_progress()
        self.assertEqual(len(progress["sessions"]), 1)
        self.assertEqual(len(progress["attempts"]), 2)
        self.assertEqual(progress["attempts"][0]["session_id"], s["session_id"])
        self.assertIn("difficulty_performance", progress["sessions"][0])
        self.assertEqual(sorted(a["topic"] for a in progress["attempts"]), ["Kanban", "Kanban"])

    def test_record_is_idempotent_by_session_id(self):
        q = bank_question("Kanban")
        record("quiz", [attempt(q, True)], session_id="20260101-000000-abcd")
        again = record("quiz", [attempt(q, True)], session_id="20260101-000000-abcd")
        self.assertTrue(again["already_recorded"])
        progress = common.load_progress()
        self.assertEqual((len(progress["sessions"]), len(progress["attempts"])), (1, 1))

    def test_atomic_write_leaves_no_temp_files(self):
        record("quiz", [attempt(bank_question("Kanban"), True)])
        self.assertEqual([p.name for p in self.data_dir.iterdir()], ["student_progress.json"])

    def test_corrupt_progress_is_never_overwritten(self):
        path = self.data_dir / "student_progress.json"
        path.write_text("{not json")
        with self.assertRaises(common.ProgressError):
            common.load_progress()
        with self.assertRaises(common.ProgressError):
            record("quiz", [attempt(bank_question("Kanban"), True)])
        self.assertEqual(path.read_text(), "{not json")
        code, out = run_json("progress_tracker.py", "--summary", data_dir=self.data_dir)
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", out["error"])

    def test_empty_history_summary_and_adaptive(self):
        self.assertEqual(progress_tracker.summarize(common.load_progress())["message"], "No sessions recorded yet.")
        rec = progress_tracker.adaptive_recommendation(common.load_progress())
        self.assertEqual(rec["suggested_difficulty"], "medium")
        self.assertEqual(rec["topic_weights"], {})
        self.assertIsNone(rec["priority_domain"])

    def test_adaptive_uses_lifetime_history_not_just_last_session(self):
        record("quiz", [attempt(bank_question("Project Charter"), False), attempt(bank_question("Triple Constraint"), False)])
        record("quiz", [attempt(bank_question("Schedule Management"), True), attempt(bank_question("Risk Management"), True)])
        rec = progress_tracker.adaptive_recommendation(common.load_progress())
        self.assertEqual(rec["suggested_difficulty_adjustment"], "increase")   # last session was perfect
        self.assertIn("Project Charter", rec["weak_topics_to_revisit"])        # ...but the old weakness is remembered
        self.assertEqual(rec["priority_domain"], "Fundamentals")
        self.assertGreater(rec["topic_weights"]["Project Charter"], rec["topic_weights"]["Risk Management"])
        for key in ("topic_weights", "suggested_difficulty_adjustment", "difficulty_note", "weak_topics_to_revisit", "domain_performance"):
            self.assertIn(key, rec)

    def test_no_priority_domain_when_everything_is_strong(self):
        record("quiz", [attempt(bank_question("Kanban"), True), attempt(bank_question("Scrum Roles"), True)])
        self.assertIsNone(progress_tracker.adaptive_recommendation(common.load_progress())["priority_domain"])

    def test_target_difficulty_staircase(self):
        def prog(*outcomes):
            return {"sessions": [], "attempts": [{"session_id": "s", "topic": "Kanban", "correct": c} for c in outcomes]}
        self.assertEqual(progress_tracker.topic_target_difficulty(prog(True)), {"Kanban": "medium"})
        self.assertEqual(progress_tracker.topic_target_difficulty(prog(True, True)), {"Kanban": "hard"})
        self.assertEqual(progress_tracker.topic_target_difficulty(prog(True, True, False, False)), {"Kanban": "medium"})
        self.assertEqual(progress_tracker.topic_target_difficulty(prog(False, False)), {"Kanban": "easy"})
        self.assertEqual(progress_tracker.topic_target_difficulty(prog(False, False, False, False, False)), {"Kanban": "easy"})

    def test_mastery_is_recency_weighted_and_shrunk_by_confidence(self):
        old_bad_new_good = {"sessions": [], "attempts": [{"topic": "Kanban", "correct": c} for c in [False] * 5 + [True] * 5]}
        old_good_new_bad = {"sessions": [], "attempts": [{"topic": "Kanban", "correct": c} for c in [True] * 5 + [False] * 5]}
        recovering = progress_tracker.topic_mastery(old_bad_new_good)["Kanban"]
        slipping = progress_tracker.topic_mastery(old_good_new_bad)["Kanban"]
        self.assertGreater(recovering["estimate"], slipping["estimate"])
        one = progress_tracker.topic_mastery({"sessions": [], "attempts": [{"topic": "Kanban", "correct": True}]})["Kanban"]
        self.assertLess(one["estimate"], 0.7)   # a single answer is not enough to call it mastered

    def test_legacy_v1_sessions_still_feed_mastery(self):
        v1 = {"sessions": [{"topic_performance": {"Kanban": {"attempted": 4, "correct": 0, "percentage": 0.0}}}]}
        mastery = progress_tracker.topic_mastery(common.upgrade_progress(v1))
        self.assertEqual(mastery["Kanban"]["attempted"], 4)
        self.assertLess(mastery["Kanban"]["estimate"], 0.5)


class TestSelector(TempDataCase):
    def setUp(self):
        super().setUp()
        self.pool = common.load_all_questions()

    def test_cold_start(self):
        chosen, meta = selector.select_questions(self.pool, 5, common.load_progress(), random.Random(1))
        self.assertEqual(meta["mode"], "cold_start")
        self.assertEqual(len(chosen), 5)

    def test_deterministic_for_a_seed_and_no_duplicates(self):
        a, _ = selector.select_questions(self.pool, 10, common.load_progress(), random.Random(3))
        b, _ = selector.select_questions(self.pool, 10, common.load_progress(), random.Random(3))
        self.assertEqual([q["id"] for q in a], [q["id"] for q in b])
        self.assertEqual(len({q["id"] for q in a}), 10)

    def test_small_pool_returns_everything(self):
        chosen, _ = selector.select_questions(self.pool[:3], 10, common.load_progress(), random.Random(1))
        self.assertEqual(len(chosen), 3)

    def test_weak_topic_is_strongly_favoured(self):
        weak, strong = bank_question("Kanban"), bank_question("Scrum Roles")
        record("quiz", [attempt(weak, False)] * 6)
        record("quiz", [attempt(strong, True)] * 6)
        progress = common.load_progress()
        picks = Counter(
            selector.select_questions([weak, strong], 1, progress, random.Random(seed))[0][0]["topic"] for seed in range(300)
        )
        self.assertGreater(picks["Kanban"], 240)

        # Nothing is excluded outright: even a mastered, just-answered question keeps a positive weight.
        mastery = progress_tracker.topic_mastery(progress)
        targets = progress_tracker.topic_target_difficulty(progress)
        history = selector.question_history(progress)
        weak_w = selector.question_weight(weak, mastery, targets, history)
        strong_w = selector.question_weight(strong, mastery, targets, history)
        self.assertGreater(strong_w, 0)
        self.assertGreater(weak_w, 50 * strong_w)

    def test_populated_history_switches_to_adaptive_mode(self):
        record("quiz", [attempt(bank_question("Kanban"), False)])
        _, meta = selector.select_questions(self.pool, 5, common.load_progress(), random.Random(1))
        self.assertEqual(meta["mode"], "adaptive")


class TestSessionEngine(TempDataCase):
    def session_file(self, sid):
        return json.loads((common.get_sessions_dir() / f"{sid}.json").read_text())

    def correct_letter(self, sid, qid):
        return next(q["correct_answer"] for q in self.session_file(sid)["questions"] if q["id"] == qid)

    def wrong_letter(self, sid, qid):
        q = next(q for q in self.session_file(sid)["questions"] if q["id"] == qid)
        return next(k for k in q["options"] if k != q["correct_answer"])

    def test_end_to_end_start_answer_answer_finish(self):
        started = session.start_session(count=2, topic="agile", seed=1)
        sid, q1 = started["session_id"], started["question"]
        self.assertEqual((started["total_questions"], q1["question_number"]), (2, 1))

        fb1 = session.submit_answer(sid, self.correct_letter(sid, q1["id"]), q1["id"])
        self.assertTrue(fb1["correct"])
        self.assertFalse(fb1["done"])
        q2 = fb1["next_question"]
        self.assertEqual(q2["question_number"], 2)

        fb2 = session.submit_answer(sid, self.wrong_letter(sid, q2["id"]), q2["id"])
        self.assertFalse(fb2["correct"])
        self.assertTrue(fb2["done"])
        self.assertIsNone(fb2["next_question"])
        self.assertTrue(ANSWER_KEYS <= set(fb2))          # feedback is available once answered

        result = session.finish_session(sid)
        self.assertEqual(result["summary"]["percentage"], 50.0)
        self.assertEqual(len(result["missed_questions"]), 1)
        self.assertFalse(result["already_recorded"])

        progress = common.load_progress()
        self.assertEqual((len(progress["sessions"]), len(progress["attempts"])), (1, 2))
        self.assertEqual(progress["sessions"][0]["session_id"], sid)
        self.assertEqual(progress["attempts"][0]["chosen"], fb1["chosen"])

        again = session.finish_session(sid)               # idempotent
        self.assertTrue(again["already_recorded"])
        self.assertEqual(len(common.load_progress()["sessions"]), 1)

    def test_key_is_never_exposed_before_answering(self):
        started = session.start_session(count=3, seed=2)
        sid = started["session_id"]
        outputs = [started, session.next_question(sid), session.session_status(sid), session.list_sessions()]
        for out in outputs:
            self.assertEqual(find_keys(out, ANSWER_KEYS), set(), out)
        qid = started["question"]["id"]
        feedback = session.submit_answer(sid, "A", qid)
        self.assertTrue(ANSWER_KEYS <= set(feedback))
        # the *next* question stays hidden, both inside the feedback payload and via `next`
        self.assertEqual(find_keys(feedback["next_question"], ANSWER_KEYS), set())
        self.assertEqual(find_keys(session.next_question(sid), ANSWER_KEYS), set())

    def test_key_and_grading_live_in_the_session_file(self):
        started = session.start_session(count=1, seed=1)
        stored = self.session_file(started["session_id"])["questions"][0]
        self.assertIn("correct_answer", stored)
        self.assertIn("explanation", stored)
        self.assertTrue(str(common.get_sessions_dir()).startswith(str(self.data_dir)))

    def test_invalid_answers_are_rejected_and_not_recorded(self):
        started = session.start_session(count=2, seed=1)
        sid, qid = started["session_id"], started["question"]["id"]
        for bad in ("Z", "", "AB", "1"):
            with self.assertRaises(session.SessionError, msg=bad):
                session.submit_answer(sid, bad, qid)
        with self.assertRaises(session.SessionError):
            session.submit_answer(sid, "A", "NOT-THE-CURRENT-QUESTION")
        self.assertEqual(session.session_status(sid)["answered"], 0)

    def test_lowercase_and_punctuated_choices_are_accepted(self):
        started = session.start_session(count=2, seed=1)
        sid, qid = started["session_id"], started["question"]["id"]
        self.assertEqual(session.submit_answer(sid, " b. ", qid)["chosen"], "B")

    def test_repeated_submission_is_idempotent(self):
        started = session.start_session(count=3, seed=1)
        sid, qid = started["session_id"], started["question"]["id"]
        first = session.submit_answer(sid, "A", qid)
        second = session.submit_answer(sid, "B", qid)      # same question again, different letter
        self.assertTrue(second["already_answered"])
        self.assertEqual(second["chosen"], "A")            # original answer stands
        self.assertEqual(second["correct"], first["correct"])
        self.assertEqual(session.session_status(sid)["answered"], 1)

    def test_finish_requires_all_answers_unless_partial(self):
        started = session.start_session(count=3, seed=1)
        sid = started["session_id"]
        with self.assertRaises(session.SessionError):
            session.finish_session(sid)                    # nothing answered
        session.submit_answer(sid, "A", started["question"]["id"])
        with self.assertRaises(session.SessionError):
            session.finish_session(sid)                    # 2 unanswered
        result = session.finish_session(sid, partial=True)
        self.assertTrue(result["partial"])
        self.assertEqual((result["summary"]["total_attempted"], result["unanswered"]), (1, 2))

    def test_finished_and_abandoned_sessions_are_closed(self):
        started = session.start_session(count=1, seed=1)
        sid = started["session_id"]
        session.submit_answer(sid, "A", started["question"]["id"])
        session.finish_session(sid)
        with self.assertRaises(session.SessionError):
            session.submit_answer(sid, "A")
        other = session.start_session(count=2, seed=1)
        session.abandon_session(other["session_id"])
        with self.assertRaises(session.SessionError):
            session.submit_answer(other["session_id"], "A")
        with self.assertRaises(session.SessionError):
            session.finish_session(other["session_id"])
        self.assertEqual(len(common.load_progress()["sessions"]), 1)   # abandoned sessions are never recorded

    def test_bad_session_ids(self):
        for sid in ("../../etc/passwd", "nope", "20260101-000000-zzzz", "20260101-000000-abcd", ""):
            with self.assertRaises(session.SessionError, msg=sid):
                session.session_status(sid)

    def test_start_validation(self):
        with self.assertRaises(session.SessionError):
            session.start_session(count=0)
        with self.assertRaises(session.SessionError):
            session.start_session(topic="xyz-nonexistent")
        with self.assertRaises(session.SessionError):
            session.start_session(domain="business acumen")
        with self.assertRaises(session.SessionError):
            session.start_session(mode="mock", topic="agile")
        with self.assertRaises(session.SessionError):
            session.start_session(mode="mock", adaptive=True)

    def test_quiz_shortfall_warning(self):
        started = session.start_session(domain="business analysis", count=50, seed=1)
        self.assertEqual(started["total_questions"], 11)
        self.assertTrue(started["warnings"])

    def test_adaptive_selection_empty_then_populated_history(self):
        empty = session.start_session(count=5, adaptive=True, seed=1)
        self.assertEqual(empty["selection"]["mode"], "cold_start")
        weak = bank_question("Kanban")
        record("quiz", [attempt(weak, False)] * 5)
        populated = session.start_session(count=5, adaptive=True, seed=1)
        self.assertEqual(populated["selection"]["mode"], "adaptive")
        self.assertEqual(find_keys(populated, ANSWER_KEYS), set())

    def test_adaptive_respects_filters(self):
        started = session.start_session(domain="predictive", count=4, adaptive=True, seed=1)
        stored = self.session_file(started["session_id"])["questions"]
        self.assertTrue(all(q["domain"] == "Predictive" for q in stored))

    def test_mock_session_uses_official_weights_and_caps(self):
        started = session.start_session(mode="mock", count=150, seed=1)
        self.assertEqual(started["total_questions"], 48)
        self.assertTrue(any("Requested 150" in w for w in started["warnings"]))
        self.assertIn("not an official PMI exam", started["disclaimer"])
        ids = [q["id"] for q in self.session_file(started["session_id"])["questions"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(started["selection"]["official_domain_weights"], taxonomy.official_weights())

    def test_mock_allow_repeats_only_when_explicit(self):
        started = session.start_session(mode="mock", count=100, seed=1, allow_repeats=True)
        self.assertEqual(started["total_questions"], 100)
        self.assertTrue(any("repeated" in w for w in started["warnings"]))

    def test_mock_finish_is_recorded_as_mock_exam(self):
        started = session.start_session(mode="mock", count=20, seed=1)
        sid, nxt = started["session_id"], started["question"]
        while nxt:
            nxt = session.submit_answer(sid, "A", nxt["id"])["next_question"]
        result = session.finish_session(sid)
        self.assertEqual(common.load_progress()["sessions"][0]["type"], "mock_exam")
        self.assertEqual(result["summary"]["total_attempted"], 20)
        self.assertIn("not an official PMI exam", result["practice_disclaimer"])

    def test_repeated_mock_questions_are_scored_each_time(self):
        started = session.start_session(mode="mock", count=60, seed=1, allow_repeats=True)
        sid, nxt = started["session_id"], started["question"]
        while nxt:
            nxt = session.submit_answer(sid, "A", nxt["id"])["next_question"]
        self.assertEqual(session.finish_session(sid)["summary"]["total_attempted"], 60)


class TestSessionCLI(TempDataCase):
    def test_start_answer_answer_finish_via_cli(self):
        code, started = run_json("session.py", "start", "--topic", "agile", "--count", "2", "--seed", "1", data_dir=self.data_dir)
        self.assertEqual(code, 0)
        self.assertEqual(find_keys(started, ANSWER_KEYS), set())
        sid, q1 = started["session_id"], started["question"]["id"]

        code, fb1 = run_json("session.py", "answer", "--session", sid, "--choice", "A", "--question-id", q1, data_dir=self.data_dir)
        self.assertEqual(code, 0)
        q2 = fb1["next_question"]["id"]
        code, fb2 = run_json("session.py", "answer", "--session", sid, "--choice", "b", "--question-id", q2, data_dir=self.data_dir)
        self.assertEqual((code, fb2["done"]), (0, True))

        code, done = run_json("session.py", "finish", "--session", sid, data_dir=self.data_dir)
        self.assertEqual(code, 0)
        self.assertEqual(done["summary"]["total_attempted"], 2)
        self.assertIn("adaptive", done)

        code, listing = run_json("session.py", "list", data_dir=self.data_dir)
        self.assertEqual(listing["sessions"][0]["status"], "finished")
        self.assertTrue((self.data_dir / "student_progress.json").exists())

    def test_errors_are_json_with_nonzero_exit(self):
        for args in (["answer", "--session", "20260101-000000-abcd", "--choice", "A"], ["start", "--topic", "xyz-nonexistent"],
                     ["status", "--session", "bad"]):
            code, out = run_json("session.py", *args, data_dir=self.data_dir)
            self.assertEqual(code, 1, args)
            self.assertIn("error", out)


class TestBackwardCompatibleCLIs(TempDataCase):
    """Existing commands and their basic behaviour must keep working."""

    def cli(self, script, *args, stdin=None):
        return run_json(script, *args, stdin=stdin, data_dir=self.data_dir)

    def test_quiz_engine_examples(self):
        for args in (["--topic", "agile", "--count", "10"], ["--topic", "schedule management", "--count", "10"],
                     ["--difficulty", "hard", "--count", "20"], ["--domain", "predictive", "--count", "10"],
                     ["--domain", "agile", "--count", "5", "--no-shuffle"]):
            code, quiz = self.cli("quiz_engine.py", *args)
            self.assertEqual(code, 0, args)
            self.assertGreaterEqual(quiz["quiz_size"], 1)
            for key in ("quiz_size", "requested_count", "filters", "questions"):
                self.assertIn(key, quiz)
        # --reveal-answers still works, but only with the explicit developer opt-in (see test_security.py)
        code, quiz = run_json("quiz_engine.py", "--count", "10", "--reveal-answers", data_dir=self.data_dir, reveal=True)
        self.assertEqual((code, quiz["quiz_size"]), (0, 10))

    def test_mock_exam_output_keys(self):
        code, exam = self.cli("mock_exam.py", "--questions", "20", "--seed", "42")
        self.assertEqual(code, 0)
        for key in ("exam_type", "requested_questions", "actual_questions", "domain_distribution_target", "warnings", "disclaimer", "questions"):
            self.assertIn(key, exam)

    def test_legacy_record_summary_adaptive_and_plan(self):
        payload = json.dumps({"attempts": [
            {"question_id": "AGILE-001", "domain": "Agile", "topic": "Scrum Roles", "difficulty": "easy", "correct": True},
            {"question_id": "PRED-001", "domain": "Predictive", "topic": "Schedule Management", "difficulty": "medium", "correct": False},
        ]})
        code, scored = self.cli("score_analyzer.py", "--stdin", stdin=payload)
        self.assertEqual((code, scored["summary"]["percentage"]), (0, 50.0))

        code, recorded = self.cli("progress_tracker.py", "--record", "--type", "quiz", "--stdin", stdin=payload)
        self.assertEqual(code, 0)
        self.assertIn("recorded_session", recorded)
        self.assertEqual(recorded["recorded_session"]["attempted"], 2)

        code, summary = self.cli("progress_tracker.py", "--summary")
        self.assertEqual((code, summary["total_sessions"], summary["lifetime_percentage"]), (0, 1, 50.0))

        code, adaptive = self.cli("progress_tracker.py", "--adaptive")
        self.assertEqual(code, 0)
        for key in ("priority_domain", "topic_weights", "suggested_difficulty_adjustment", "weak_topics_to_revisit", "domain_performance"):
            self.assertIn(key, adaptive)

        code, plan = self.cli("study_plan.py", "--weeks", "8", "--hours-per-week", "10")
        self.assertEqual((code, len(plan["plan"])), (0, 8))
        self.assertIn("disclaimer", plan)
        code, plan = self.cli("study_plan.py", "--weeks", "2", "--hours-per-week", "5", "--ignore-history")
        self.assertEqual((code, len(plan["plan"])), (0, 2))

    def test_legacy_record_with_no_attempts_fails_cleanly(self):
        code, out = self.cli("progress_tracker.py", "--record", "--stdin", stdin='{"attempts": []}')
        self.assertEqual(code, 1)
        self.assertIn("error", out)

    def test_progress_tracker_without_flags_prints_help(self):
        code, out, _ = run_cli("progress_tracker.py", data_dir=self.data_dir)
        self.assertEqual(code, 0)
        self.assertIn("usage", out.lower())


def _real_session_files():
    real_sessions = ROOT / "data" / "sessions"
    return sorted(p.name for p in real_sessions.glob("*.json")) if real_sessions.exists() else []


_REAL_SESSIONS_BEFORE_TESTS = _real_session_files()  # snapshot taken when the module is imported, before any test runs


class TestRealDataUntouched(unittest.TestCase):
    def test_test_suite_did_not_touch_real_sessions(self):
        # Compares against a snapshot so real tutoring sessions (git-ignored) never make this fail.
        self.assertEqual(_real_session_files(), _REAL_SESSIONS_BEFORE_TESTS)


if __name__ == "__main__":
    unittest.main()
