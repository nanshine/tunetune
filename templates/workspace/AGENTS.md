# Research workspace

Help the person turn a need into a useful model: researched proposal, calibrated evaluation, baseline, bounded experiments and verified delivery. Explain consequential choices in ordinary language and perform routine commands yourself. The panel observes the same files through an experiment canvas and research views; its only write action is changing the project name. Requests and user decisions stay in conversation.

## Start and continue

Load `research-workspace`, then the relevant sibling: `tunetune-init`, `build-evaluation`, `train` or `review`. Skills live in `.agents/skills/`, or `.claude/skills/` for that host. If named loading is unavailable, read the corresponding `SKILL.md` directly.

Read the shared skill's `references/records.md` for format 2 and `references/tools.md` before using its scripts. `project.schema_version` identifies the format; `.workspace/manifest.json` identifies installed tools. Refuse incompatible projects rather than migrating them.

Begin with `proposal.json`, relevant resources and evaluation evidence, then follow the experiments needed for the next decision. Create research files and their parents only when needed. Update the current proposal and relevant `analysis.json` with conflict detection rather than building a second ledger.

## Research principles

- Carry the user's exact authorization across skills and bounded rounds. Ask only for consequential missing decisions or changed access, privacy, scope or spending boundaries.
- Calibrate the actual scoring path and separate development examples from independent final checks.
- Establish a usable baseline, count failures and retests against a finite budget, and reserve final-validation time.
- Preserve fixed inputs and terminal measurements. Use fresh IDs for retries and experiment-local evaluations; retesting does not require retraining.
- Verify actual outputs before success. Inspect real processes and logs before resuming; a status field alone does not prove liveness.
- Coordinate one writer and preserve path, symlink and private-data protections. Optional resource observations are limited facts, not suitability judgments.
- Keep verified models inside experiments and chosen experiment IDs in `project.deliveries`. Selection does not deploy or copy a model. Export separately only when requested.
- Report limitations and unmet requirements; an untrained fallback does not fulfill an explicit training request.

## Open the panel

```sh
python3 .workspace/app/workspace.py --project . --port 0 --open
```

Use the actual printed address. Keep the service in a managed session and provide a link if opening is unavailable. The panel needs neither Node nor product source. Closing it does not stop independent commands; leaving it open does not schedule autonomous research.
