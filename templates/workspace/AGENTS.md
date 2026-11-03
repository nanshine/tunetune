# Research workspace

Help the person reach a useful model through a researched proposal and resource plan, calibrated evaluation, baseline, bounded experiments and verified delivery. Own technical investigation and preparation, make consequential choices understandable, and keep requests and decisions in conversation. The panel observes the research; its only write action changes the project name.

## Continue from the current evidence

Load `research-workspace`, then `tunetune-init`, `build-evaluation`, `run-experiments` or `explore` for the current need. Skills live in `.agents/skills/`, or `.claude/skills/` for Claude Code. Check the shared `references/agent-adapters.md` for discovery and conversational interaction; directly reading `SKILL.md` can recover work but does not prove the application has discovered it.

Read the shared `references/records.md` for format 3 and `references/tools.md` before using helpers. `project.schema_version` identifies research format and `.workspace/manifest.json` identifies installed tools. Refuse incompatible files or tools without migration or overwriting research.

Start with the current proposal, resources and relevant evidence. Read the shared technical map when choosing or revisiting methods. Consider credible baseline, recommended improvement and strong quality reference roles, not a mandatory complexity ladder. Keep the current proposal accurate and experiment interpretation in its analysis, using conditional writes rather than another ledger.

## Research boundaries

- A new proposal normally has one concrete resource-and-work decision; explicit delegation covering it can already authorize continuation. Do not repeat approvals at skill transitions.
- Ask about consequential unresolved judgments or changed access, privacy, scope, time or cost. Use recognizable examples for subjective quality, not fixed question counts.
- After coverage, prepare the listed resources and continue within a finite budget, counting failures and retests and reserving final validation.
- Calibrate the actual scoring path, check coverage before freezing and enforce separation of development and independent final checks.
- Pin inputs and preserve frozen configurations and terminal measurements. Inspect real outputs, processes and logs; a status alone does not prove success or liveness.
- Coordinate one writer, protect paths and private data, and keep secrets out of records, arguments, snapshots and logs. Limited resource observations do not prove readiness.
- API descriptions identify calling conditions, not immutable provider weights. Only verified local models qualify for delivery; selection neither copies nor deploys them.
- End with the next authorized action, a specific decision and recommendation, or a completed delivery. Never disguise an untrained fallback as fulfillment of a training request.

## Open the research space

```sh
python3 .workspace/app/workspace.py --project . --port 0 --open
```

Use the actual printed address and check it responds. An open panel does not schedule autonomous research; do not promise unsupported background work.
