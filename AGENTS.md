# Repository Guidelines

## Product and Structure

TuneTune helps beginners build useful private models through file-driven research. Follow [the product principles](docs/principles.md): researched proposal → calibrated evaluation → baseline → bounded experiments → usable delivery. Preserve the infinite experiment canvas and the floating proposal, plan, resource, evaluation and acceptance windows. The panel shows research, records the person's hash-bound responses under `responses/`, runs verified local models for acceptance and trial inputs, and edits `project.json.name`; research records are written only by the Agent. Work starts, stops and changes boundaries in the Agent conversation.

Skills are concise English instructions for general research and judgment, not task-specific recipes or duplicate schemas. Give each boundary its reason so the Agent can apply it to situations the skill does not name. Repeatable mechanics belong in deterministic scripts. Continue across skills and bounded rounds within the user's exact current authorization; ask only for missing consequential decisions or changed access, privacy, scope or cost boundaries. Explain uncertainty and unmet requirements honestly.

- `workspace/src/`: React/TypeScript panel source, model logic, CSS and colocated Vitest tests. Its build output goes to `skills/research-workspace/assets/panel/` and is committed.
- `skills/`: three research workflows plus shared `research-workspace`, the unit every channel distributes. Its `references/records.md` is the canonical format-4 guide; `references/tools.md` documents `scripts/init.py`, `scripts/records.py`, `scripts/run.py`, `scripts/resources.py` and the read-only `scripts/scout.py`. `scripts/workspace.py` serves the panel; sibling `monitor.py` provides limited optional resource observations. `assets/templates/` holds only the installed agent guide and minimal project, proposal and resource files; create research directories when needed and include no sample research data. `manifest.json` pins the files `init.py` copies into a project.
- `.claude-plugin/`, `.codex-plugin/` and `.agents/plugins/`: plugin manifests over `skills/`. `INSTALL.md`: the Agent's installation path from the README sentence.
- `scripts/`: manifest and local demo tools. `tests/`: Python integration and safety tests.
- `design/` and `reference/`: local supporting assets, excluded from distribution.

## Build, Test and Development

Use Node.js 22.12+ and Python 3.10+ on macOS/Linux. From the repository root:

```sh
npm --prefix workspace ci
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
python3 scripts/build-skills.py
```

Rebuild the panel and rerun `build-skills.py` whenever a distributed script, template or the panel changes; tests fail on a stale manifest. For development, run `python3 skills/research-workspace/scripts/workspace.py --project /absolute/my-research --assets skills/research-workspace/assets/panel --port 8765` against an initialized project, then `npm --prefix workspace run dev -- --port 5173`; Vite proxies `/api` to port 8765.

## Conventions and Validation

Match existing style: two-space indentation, single quotes and semicolons in TypeScript; four-space indentation and snake_case in Python. Use PascalCase component filenames, camelCase TypeScript functions and `use`-prefixed hooks. TypeScript checks strictness and unused code; no formatter or lint script is configured.

Name frontend tests `*.test.ts` and Python tests `test_*.py`. Add regression coverage for changed parsing, execution, filesystem safety or distribution behavior. Generate fixtures in temporary directories. Run both suites and the frontend build; report failures rather than bypassing checks. Commit only when requested, using concise imperative subjects. PRs should explain behavior changes, relevant issues and validation, with screenshots for UI changes.

## Evidence and Distribution Safety

Preserve conflict detection, immutable configurations and terminal measurements, verified inputs, path and symlink protections, and project isolation. Update the current proposal and experiment analyses in place through conditional writes. Keep evidence exploration inside run-experiments rounds; the experiment plan is the only round record. Selected models remain experiment-local; comparison contains outputs, and selection implies neither deployment nor user satisfaction.

Keep file mechanics in the canonical shared guide, with no project-root copy. Tools 0.7.0 support schema 4 only: explicitly refuse incompatible projects and projects pinned to other tool versions, without automatic migration or overwriting research. Distribute only the four sibling skill folders, with the required record and run helpers, service and monitor helper, minimal templates and built panel inside the shared skill; exclude secrets, research outputs, frontend source and dependencies.
