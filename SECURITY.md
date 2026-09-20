# Security model and limitations

The CAPM tutor is a **single-student, local** tool that runs inside Claude Code as one OS user. There is no server, no network service and no other user. It handles untrusted text (student messages, pasted documents, tool output) and protects two things: **answer keys** (quiz integrity) and **the student's own data**.

This is defence-in-depth, not a guarantee. Nothing here makes prompt injection impossible, and a determined attacker with control of the model's actions or the machine can get around it.

## Layers, and how strong each one is

| Layer | What it does | Enforced by | Strength |
|---|---|---|---|
| **Instruction level** | Student text, pasted documents, external content and tool output are data, not instructions; never build shell commands from student text; never reveal keys, prompts or secrets | `SKILL.md`, `CLAUDE.md` | **Advisory.** Depends on the model following them. A successful injection can defeat this layer, so the layers below do not rely on it. |
| **Application (code) level** | Tools have no shell, `eval`/`exec`, network or dynamic imports. Arguments are allowlisted or validated (option letter, ids, topic/domain). Free text is capped and stripped of control/zero-width/bidi characters. Persisted attempt fields are strictly shaped and stored notes are never shown back to the tutor. Counts, weeks, hours, attempts and input size are capped. Non-UTF-8 and over-nested input fail cleanly. Session and bank files cannot be read through `--input`. Bank text is sanitised on load and checked by `validate_bank.py`. Error messages truncate echoed input. | `tools/*.py` | **Enforced**, and covered by `tests/test_security.py`. |
| **Tool authorization** | `--reveal-answers` (which prints the whole answer key) is refused unless a developer opt-in is set. Claude Code deny rules block reading, editing or writing session files, reading the question bank, editing the progress file, dumping the environment, and any shell text that mentions those paths. | code + `.claude/settings.json` | **Best effort.** Deny rules match command *text*. Obfuscation (globs such as `sess*`, `cd` then relative paths, variable expansion, encoding) can evade them. They are not a sandbox. |
| **Data isolation** | Session and progress files are written owner-only (`0600`), atomically. | OS file permissions | **Weak.** Any process running as the same user can read them. There is no per-user isolation because there is only one user. |

## What is and is not protected

**Protected (by code):**
- The answer key is never printed by `start`, `next`, `status`, `list` or a partial `finish`. Feedback for a question exists only after it has been answered, and answers must be submitted in order with the matching question id.
- No tool reads environment variables other than `CAPM_DATA_DIR` and the developer opt-in flag, so tools cannot leak secrets.
- Student-controlled fields that are persisted and later shown to the tutor cannot carry free text: `chosen` is one letter, `answered_at` an ISO-8601 timestamp, `question_id` a short id. Free-text notes are capped and cleaned and are not returned by any tool.
- Path traversal through session ids is rejected, and generic `--input` paths that resolve (including via symlinks) into the sessions directory or the question bank are refused.

**Not protected, and known limitations:**
- **Model behaviour.** Whether the model resists "ignore previous instructions", refuses to reproduce system/developer instructions, or avoids interpolating text into a shell command cannot be verified by unit tests. It is reviewed manually (`evals/eval.md` §3.7) and remains probabilistic.
- **Shell command construction happens before Python runs.** If the agent pastes raw student text into a Bash command, the shell parses it first and no Python-side validation can help. The mitigation is the allowlist rule in the skill; the code-level tools are inert to shell metacharacters only once they receive them as plain arguments.
- **Short text can still pass through shaped fields** (for example a 40-character `question_id`). It is limited, not eliminated.
- **Visible instructions inside bank content are not removed.** Only hidden characters are stripped and lengths capped. Bank content is trusted repo content (reviewed via `validate_bank.py`), and tools return it only inside data fields.
- **`SKILL.md` and `CLAUDE.md` are not secret.** They are committed to a public repository. The tutor declines to reproduce *platform and developer* instructions and secrets; it cannot make repository files confidential.
- **The answer key is on disk** in the session file, and the whole bank is on disk. Deny rules reduce accidental or injected access by the agent; they do not stop the machine's owner or other same-user processes.
- **No multi-user model.** "Another student's data" does not exist in this design. Supporting several students would need authentication and per-user storage, which this project does not have.
- **External content** (web pages, PDFs, uploads) is handled only by the model. The tools never fetch or parse it, so their protection does not cover it; the instruction-level rule applies.

## For maintainers

- `--reveal-answers` (quiz and mock) prints answer keys. It works only when the environment variable `CAPM_ALLOW_REVEAL_ANSWERS=1` is set in *your own* terminal; it is for tests and bank maintenance, never tutoring. The test suite sets it explicitly.
- The shipped `.claude/settings.json` is tuned for **tutoring**. Editing the question bank with Claude Code needs the `Read`/`Bash` deny rules for `question_bank` to be lifted temporarily (edit the file, or work from a separate checkout). Restore them afterwards.
- Run `python3 -m unittest discover -s tests` and `python3 tools/validate_bank.py` after changing tools or bank content.
- If you find a way to extract answer keys or run commands from student text, please open an issue or contact the maintainer privately.
