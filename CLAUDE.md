# Livestock Monitoring IoT — instructions for Claude Code

## Read first
- project_overview.md (repo root): short summary of the project.
- For details, open project_master_handoff.md or project_architecture.md,
  reading headings first, then only the sections you need. They are long.
- If the overview and a reference file disagree, the reference file wins.
- Current work status: the latest docs/work_status_*.md file.

## Working rules
- Always propose a plan and wait for my approval before editing files.
- Feature freeze: no new features unless I ask explicitly.
- Git: read-only (status, diff, log). Never branch, add, mv, rm, commit, stash, reset, push.
- Never modify .env or m5stack/device_config.py; never flash firmware.
- Tests: only through scripts/run_isolated_tests.py or a disposable database.
  Never connect to livestock_dev or livestock_bench.
- Every test total is reported with commit, command and date.
- Code and comments in English.

## Project rules
- Never invent a measurement timestamp when the device has no reliable UTC.
- No automatic diagnosis from behavioral anomalies.
- Sampling frequency ≠ transmission frequency.
- A proposal is not a fact until decided and validated.
- If unsure about a fact in the docs, mark it [to verify] instead of guessing.