# Adapters: the same agent in other IDE agents

One folder, one bootstrap, one hook. Every environment gets the same three things, delivered the
way that environment expects them:

1. **Entry file** that leads to `AGENTS.md` (read natively, or through a one-line `@AGENTS.md`
   import in `CLAUDE.md`, `QWEN.md`, `GIGACODE.md`, `GEMINI.md`).
2. **Session-start hook**, where the environment has one: its config calls the one script
   `hooks/session-start` with `--format <env>`, and the script prints the bootstrap skill plus
   `bin/strat state` under the output key that environment reads. Without `--format` the script
   detects the environment by its variables; Claude Code's output is unchanged. Where no hook
   exists, `AGENTS.md` tells the agent to run `bin/strat state` first.
3. **Skills** where the environment looks for them. `.agents/skills` and `.gigacode/skills` are
   symlinks to `skills/`, so there is one copy and nothing to sync. `tests/test_adapters.py`
   fails if a link breaks or is replaced by a copy.

Pattern: obra/superpowers v7.0.2 (`hooks/session-start`, `hooks/hooks.json`,
`hooks/hooks-cursor.json`, `docs/porting-to-a-new-harness.md`), adapted from a plugin to a
project folder: we ship project-level config, not a plugin manifest.

## Status

"Run end to end" means: a case was created and two steps were logged as Claude Code would log
them, then the other environment was started headless in a fresh clone with the prompt
"Продолжи кейс"; it read the bootstrap, ran `bin/strat state`, named the stage and the next action
and did not repeat a logged step. "Config written, not run" means the files follow the vendor's
current docs and the hook command passes `tests/test_adapters.py` (which runs it with the
variables that environment sets), but the environment itself was not started.

| Environment | Files | Session-start hook | Skills found at | Status |
|---|---|---|---|---|
| Claude Code | `CLAUDE.md` -> `AGENTS.md`, `.claude/settings.json` | yes, `hookSpecificOutput.additionalContext` | `skills/` via `AGENTS.md` and the hook; `.claude/skills` is planned for `strat setup --sync` (not built yet) | run end to end (Phase 1) |
| Codex CLI | `AGENTS.md` | none (Codex finds skills itself; superpowers dropped its hook) | `.agents/skills` | run end to end, see Evidence |
| omp (oh-my-pi) | `AGENTS.md` (also loads `CLAUDE.md`) | none needed; `AGENTS.md` bootstrap | `.agents/skills` | run end to end, see Evidence |
| Qwen Code | `QWEN.md` -> `AGENTS.md`, `.qwen/settings.json` | `SessionStart`, `--format qwen` -> `hookSpecificOutput.additionalContext` | `.agents/skills` | run end to end, see Evidence; the hook ran only with folder trust |
| Cursor | `AGENTS.md`, `.cursor/rules/strategist.mdc` (`alwaysApply`), `.cursor/hooks.json` | `sessionStart`, `--format cursor` -> `additional_context` | `.agents/skills` | config written, not run |
| GigaCode | `GIGACODE.md` -> `AGENTS.md` (it also reads `AGENTS.md`), `.gigacode/rules/strategist.md` (`apply: ALWAYS`), `.gigacode/settings.json` | `SessionStart` in the Qwen Code format, `--format gigacode` | `.gigacode/skills` | config written, not run; the hook format is inferred from Qwen Code (GigaCode's docs do not describe hooks) |
| Copilot CLI | `AGENTS.md`, `.github/hooks/strategist.json` | `sessionStart`, `--format copilot` -> `additionalContext` | `.agents/skills` | config written, not run |
| Gemini CLI | `GEMINI.md` -> `AGENTS.md`, `.gemini/settings.json` | `SessionStart`, `--format gemini` -> `hookSpecificOutput.additionalContext` | `.agents/skills` (workspace must be trusted) | config written, not run |
| OpenCode | `AGENTS.md` | none; `AGENTS.md` bootstrap (no JS plugin shipped) | `.agents/skills` | config written, not run |
| Pi | `AGENTS.md` | none; `AGENTS.md` bootstrap (no TS extension shipped) | `.agents/skills` | config written, not run |
| Kimi Code | `AGENTS.md` | none | `.agents/skills` | config written, not run |
| Devin, Hermes, OpenClaw | - | - | - | not done (last priority) |

Notes:

- Qwen Code and Gemini CLI run a project hook only after the user trusts the folder or approves
  the hook once (Qwen: interactively, or `--yolo` on the command line). Until then the
  `AGENTS.md` bootstrap still applies.
- GigaCode's hook command falls back from `GIGACODE_PROJECT_DIR` to `QWEN_PROJECT_DIR`,
  `CLAUDE_PROJECT_DIR` and the current directory, because GigaCode does not document its hook
  variables. Confirm on a real install.
- OpenCode and Pi load a session-start bootstrap only through code plugins (superpowers ships
  `.opencode/plugins/superpowers.js` and `.pi/extensions/superpowers.ts`). We did not ship
  untested plugin code; `AGENTS.md` does the same job one step later (the agent runs
  `bin/strat state` itself).
- Symlinks need `core.symlinks=true` on Windows; without it `.agents/skills` becomes a text file
  and the environment falls back to reading `skills/` through `AGENTS.md`.
- If `.claude/skills` is added later, it and `.agents/skills` will hold the same skills; Copilot CLI and
  OpenCode read both and may list each skill twice.

## Evidence

All runs: 2026-11-15, a fresh `git clone` of this branch under a scratch folder, case
`adapters-test` (synthetic, no materials) created with `bin/strat new`, then
`bin/strat step intake.questions` and `bin/strat step intake.brief --stage plan --next "Plan: ..."`
as Claude Code logs them. State before each run: stage `plan`, steps `intake.questions,
intake.brief`. Prompt: "Продолжи кейс". Every run was headless and sandboxed (macOS
`sandbox-exec`: no writes outside the scratch folder, no reads of other projects or agent configs).

| Run | Model, mode | What it did | Time, tokens, cost |
|---|---|---|---|
| Codex CLI 0.166.0 | `gpt-6-luna`, effort low, `codex exec -s read-only` | read `skills/using-strategist/SKILL.md`, ran `bin/strat state`, named stage `plan`, read `skills/plan/SKILL.md` and the brief; replied in Russian with the stage and that the next action is drafting options and the decision table; did not redo intake. It could not write (read-only), so it stopped and said so. `codex debug prompt-input` lists all 14 skills with the skill root at `skills/` (resolved through `.agents/skills`). | 27 s; 93k input (82k cached), 1k output; ChatGPT subscription, no direct charge |
| omp 18.2.7 | `anymodel/ds/deepseek-v4-flash`, thinking low, `omp -p --approval-mode yolo --max-time 5m` | read `skill://using-strategist` (found through `.agents/skills`), ran `bin/strat state`, said "стадия `plan`", read `skill://plan`, logged `plan.options`, `plan.table`, `plan.plan`, stopped at Gate 1 asking for the user's yes. Log: `intake.questions, intake.brief, plan.options, plan.table, plan.plan`; intake not repeated, gate not approved. | 4 min 42 s; 645k input, 19.6k output; about 194k AnyModel balance tokens |
| Qwen Code 0.27.3, no folder trust | `ds/deepseek-v4-flash` on the AnyModel OpenAI-compatible endpoint, `qwen --yolo -o stream-json` | stderr: "Project hooks in .qwen/settings.json were not loaded: the folder is not explicitly trusted". Through `QWEN.md` -> `AGENTS.md` it read the bootstrap skill, ran `bin/strat state`, said "Кейс `adapters-test` на стадии plan", logged nine `plan.claims.*` steps and `plan.options`, `plan.table`, `plan.plan`, ran `bin/strat gate check 1`, stopped and asked for an explicit yes. Intake not repeated, gate not approved. Skills from `.agents/skills` appear among its slash commands (e.g. `data-analysis`). | 4 min 18 s; 650k input, 28.7k output; about 189k balance tokens |
| Qwen Code 0.27.3, folder trusted | same model; user settings `security.folderTrust.enabled` and the clone in `trustedFolders.json` | prompt forbade tools and asked for the active case, stage and next action. One turn, no tool calls; it answered "кейс adapters-test, стадия plan, следующее действие: черновые варианты, таблица решений, вопросы исследования (`skills/plan`)". The request it sent contained the `<strategist-bootstrap>` and `<strategist-state>` blocks from `hooks/session-start --format qwen`. | 6 s; 17k input, 161 output; about 14k balance tokens |

Balance-token figures are the AnyModel balance before and after each run, so they are an upper
bound if anything else used the same account at the time.

## Docs used (fetched 2026-11-15)

| Environment | Doc |
|---|---|
| superpowers | https://github.com/obra/superpowers (tag v7.0.2), `docs/porting-to-a-new-harness.md` |
| Cursor | https://cursor.com/docs/hooks, https://cursor.com/docs/rules, https://cursor.com/docs/skills (through Context7 `/websites/cursor`) |
| Qwen Code | https://qwenlm.github.io/qwen-code-docs/en/users/features/hooks/, https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/ |
| GigaCode | https://gitverse.ru/docs/ai/ai-assistant-gigacode/gigacode-cli/memory/, .../gigacode-cli/skills/, .../basic-terms/rules/ |
| Codex | https://github.com/openai/codex `codex-rs/ext/skills/src/host_roots.rs` (through Context7 `/openai/codex`) |
| Copilot CLI | https://docs.github.com/en/copilot/reference/hooks-configuration, https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills, https://github.com/github/copilot-cli changelog |
| Gemini CLI | https://github.com/google-gemini/gemini-cli `docs/hooks/reference.md`, `docs/hooks/index.md`, `docs/cli/using-agent-skills.md` |
| OpenCode | https://github.com/anomalyco/opencode `services/site/src/docs/content/skills.mdx` |
| Pi | https://github.com/earendil-works/pi `packages/coding-agent/docs/skills.md`, `docs/extensions.md` |
| omp | https://github.com/can1357/oh-my-pi `docs/context-files.md`, `docs/config-usage.md`, `docs/skills.md`; `omp --help` (v18.2.7) |
| Kimi Code | https://github.com/moonshotai/kimi-code `docs/en/customization/skills.md` |
