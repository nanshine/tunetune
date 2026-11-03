# Repository Guidelines

## Product and Structure

TuneTune helps beginners build useful private models through file-driven research. Follow [the product principles](docs/principles.md): researched proposal → calibrated evaluation → baseline → bounded experiments → usable delivery. Preserve the infinite experiment canvas and readable proposal, resource, evaluation and comparison views. The panel observes research; its only write action is editing `project.json.name`. Requests and user decisions stay in the Agent conversation.

Skills are concise English instructions for general research and judgment, not task-specific recipes or duplicate schemas. Give each boundary its reason so the Agent can explain it to the person instead of citing the rule. Repeatable mechanics belong in deterministic scripts. Continue across skills and bounded rounds within the user's exact current authorization; ask only for missing consequential decisions or changed access, privacy, scope or cost boundaries. Explain uncertainty and unmet requirements honestly.

- `workspace/src/`: React/TypeScript components, model logic, CSS and colocated Vitest tests. `workspace/workspace.py` serves files; sibling `monitor.py` provides limited optional resource observations.
- `skills/`: three research workflows plus shared `research-workspace`. Its `references/records.md` is the canonical format-3 guide; `references/tools.md` documents `scripts/records.py`, `scripts/run.py`, `scripts/resources.py` and the read-only `scripts/scout.py`.
- `templates/workspace/`: only the installed agent guide and minimal project, proposal and resource files. Create research directories when needed; include no sample research data.
- `scripts/`: packaging, installation and local demo tools. `tests/`: Python integration and safety tests.
- `design/` and `reference/`: local supporting assets, excluded from distribution. `dist/`: generated kits.

## Build, Test and Development

Use Node.js 22.12+ and Python 3.10+ on macOS/Linux. From the repository root:

```sh
npm --prefix workspace ci
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
python3 scripts/build-kit.py
```

Packaging refuses existing versioned outputs; use `--output /absolute/fresh-output` for another build. For development, run `python3 workspace/workspace.py --project /absolute/my-research --assets workspace/dist --port 8765` against an installed project, then `npm --prefix workspace run dev -- --port 5173`; Vite proxies `/api` to port 8765.

## Conventions and Validation

Match existing style: two-space indentation, single quotes and semicolons in TypeScript; four-space indentation and snake_case in Python. Use PascalCase component filenames, camelCase TypeScript functions and `use`-prefixed hooks. TypeScript checks strictness and unused code; no formatter or lint script is configured.

Name frontend tests `*.test.ts` and Python tests `test_*.py`. Add regression coverage for changed parsing, execution, filesystem safety or distribution behavior. Generate fixtures in temporary directories. Run both suites and the frontend build; report failures rather than bypassing checks. Commit only when requested, using concise imperative subjects. PRs should explain behavior changes, relevant issues and validation, with screenshots for UI changes.

## Evidence and Distribution Safety

Preserve conflict detection, immutable configurations and terminal measurements, verified inputs, path and symlink protections, and project isolation. Update the current proposal and experiment analyses in place through conditional writes. Keep evidence exploration inside run-experiments rounds; the experiment plan is the only round record. Selected models remain experiment-local; comparison contains outputs, and selection implies neither deployment nor user satisfaction.

Keep file mechanics in the canonical shared guide, with no project-root copy. Kit 0.5.0 supports schema 3 only: explicitly refuse incompatible projects and tool versions, without automatic migration or overwriting research. Distribute the four sibling skills, required record and run helpers, service and monitor helper, minimal templates and built assets; exclude secrets, research outputs, frontend source and dependencies.
