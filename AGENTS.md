# Repository Guidelines

## Project Structure & Module Organization

TuneTune is a file-driven research workspace: agents operate research records, while the UI provides read-only research views and result comparisons. Its only write action is direct editing of the project name (`project.json.name`); it does not collect feedback, start training, or maintain a business database. Goal/resource clarification, evaluation answers, candidate/experiment feedback, research reviews, and acceptance generation requests, preferences, and decisions belong in the Agent client, not panel forms or a review entry point.

- `workspace/src/`: React and TypeScript components, model logic, CSS, and colocated Vitest tests; `workspace/workspace.py` provides the Python standard-library file service.
- `skills/`: four research workflows plus the shared `research-workspace` skill. Its `references/records.md` is the canonical record contract, and `scripts/records.py` implements record utilities.
- `templates/workspace/`: minimal research-project files and the installed project's agent guide; keep sample research data out of templates.
- `scripts/`: packaging and installation tools; `tests/`: Python integration and safety tests.
- `design/` and `reference/`: local design assets and supporting material, excluded from distributions; `dist/` contains generated release artifacts.

## Build, Test, and Development Commands

Use Node.js 22.12+ and Python 3.10+ on macOS/Linux. Run from the repository root:

```sh
npm --prefix workspace ci                 # Install locked frontend dependencies
npm --prefix workspace run build          # Type-check and build frontend assets
npm --prefix workspace test               # Run Vitest
python3 -B -m unittest discover -s tests -v # Run Python tests
python3 scripts/build-kit.py              # Package prebuilt assets and skills
```

Packaging refuses existing versioned outputs; use `--output /absolute/fresh-output` for another build. For development, run `python3 workspace/workspace.py --project /absolute/my-research --assets workspace/dist --port 8765` against an installed research project, then `npm --prefix workspace run dev -- --port 5173`; Vite proxies `/api` to port 8765.

## Coding Style & Naming Conventions

Match existing code: two-space indentation, single quotes, and semicolons in TypeScript; four-space indentation and snake_case in Python. Use PascalCase component filenames, camelCase TypeScript functions, and `use`-prefixed hooks. TypeScript enables strict and unused-code checks; no formatter or lint script is configured.

## Testing Guidelines

Name frontend tests `*.test.ts` and Python tests `test_*.py`. Add regression coverage for changed record parsing, feedback handling, filesystem safety, or distribution behavior. Generate fixtures in temporary directories. No numeric coverage threshold is configured; run both suites and the frontend build before submitting.

## Commit & Pull Request Guidelines

Git history contains only `Initial commit`; use concise imperative subjects. PRs should explain behavior changes, link relevant issues, report validation commands, and include screenshots for UI changes.

## Record & Distribution Safety

Preserve conflict detection, immutable results, path and symlink protections, and project isolation. Keep research materials, Agent review capabilities, historical feedback, and the feedback file protocol. Agents may record necessary decision evidence from user conversations, with its source and context, but conversational opinions and recorded feedback do not automatically authorize execution. Edit the canonical contract rather than generated copies, and exclude secrets, research outputs, source files, and dependencies from release kits.
