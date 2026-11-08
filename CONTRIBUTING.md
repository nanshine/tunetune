# Contributing to TuneTune

[Report a problem](https://github.com/nanshine/tunetune/issues), share a real study, or propose a change. For a bug, include what you expected, what happened, and the relevant steps or logs; remove credentials and private research data before sharing.

## Develop and validate

Use Node.js 22.12+ and Python 3.10+ on macOS or Linux. From the repository root:

```sh
npm --prefix workspace ci
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
python3 scripts/build-skills.py
```

The React/TypeScript panel lives in `workspace/src/`; distributed skills and Python tools live in `plugins/tunetune/skills/`. When changing the panel, distributed scripts, or templates, rebuild the panel and regenerate the skill manifest with `build-skills.py`, then run both test suites against the final files. Commit the built panel and manifest with the source changes.

For live panel development, initialize a temporary research project, start its workspace service with the local panel assets, then run Vite:

```sh
python3 plugins/tunetune/skills/research-workspace/scripts/workspace.py --project /absolute/my-research --assets plugins/tunetune/skills/research-workspace/assets/panel --port 8765
npm --prefix workspace run dev -- --port 5173
```

Use two-space indentation, single quotes, and semicolons in TypeScript; use four-space indentation and snake_case in Python. Add regression coverage for changes to parsing, execution, filesystem safety, or distribution, using temporary directories for generated fixtures.

## Submit a pull request

Explain the problem, the resulting behavior, and how you validated it. Include screenshots for UI changes and link any relevant issue. Keep secrets, research outputs, dependencies, and unrelated changes out of the pull request; preserve existing evidence and project isolation.

See [product principles](docs/principles.md) for research behavior and [releasing](docs/releasing.md) for distribution and release checks. Repository instructions for coding agents are in [AGENTS.md](AGENTS.md).
