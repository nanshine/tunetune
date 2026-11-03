# Start a TuneTune project

Handle setup for the person, then continue into `tunetune-init` using their original request and language.

## Obtain a trusted kit

Use the repository supplied by the user; the canonical repository is https://github.com/nanshine/tunetune. Inspect its latest published GitHub release and select its actual `workspace-kit-<version>.tar.gz` asset. Use that asset's download URL and keep all components from one bundle. Do not guess URLs or substitute a third-party download.

Download outside the project to a temporary directory. Extract only ordinary files and directories, rejecting absolute paths, traversal, links and special files. Python 3.12+ tarfile's data filter can be combined with an explicit file/directory check. Read the bundled installer before running it. Manifest hashes check integrity, not publisher identity.

Check Python 3.10+ on macOS/Linux. Use only trusted installation mechanisms within the host's permissions if prerequisites are missing. Explain unavoidable user actions plainly. If no compatible kit has been published, say so; a source build is a developer fallback only when requested.

## Install without replacing research

Inspect existing instructions and files. Kit 0.4.0 supports schema 2 only; refuse older or incompatible projects without automatic migration. Substitute the actual bundle and project paths:

```sh
python3 <bundle>/install-workspace.py --kit <bundle> --project <current-directory> --host agents
```

Use `--host claude` for Claude Code. The default installs all five sibling skills under `.agents/skills/`; the Claude option uses `.claude/skills/`. If the host cannot rediscover them immediately, read their `SKILL.md` files directly. No global installation is needed.

The installer adds only `AGENTS.md`, `project.json`, `proposal.json`, `resources.json`, the skills and `.workspace` application files. It creates only their required parent directories, not empty research stages. It preserves existing project instructions and compatible research, and refuses conflicting tool files. If existing instructions need integration, explain the installed entrypoint without replacing them; merge only within the user's authorization. The format and tool guides live in the shared skill, with no project-root duplicate.

## Open and continue

Start the local service in a managed session:

```sh
python3 .workspace/app/workspace.py --project . --port 0 --open
```

Check the actual printed URL responds before reporting success. `--open` requests the system browser; provide a clickable link if opening is unavailable. The panel observes research and comparisons, with project-name editing as its only write action. Requests and decisions remain in conversation.

Load `research-workspace` and `tunetune-init`, investigate enough to present a useful proposal, and continue within the existing authorization. Explain what is ready and what is limited. Optional resource monitoring is not a suitability test, and an open panel does not schedule autonomous work. Downloads, training dependencies, paid resources and private-data transfers wait until needed and authorized.
