# Start a TuneTune study

Handle installation and discovery, preserve the person's original request and language, then continue into `tunetune-init`. Default to the current conversation directory; do not silently create a child study directory.

## Obtain one compatible kit

Use the user-supplied repository, normally https://github.com/nanshine/tunetune. Inspect published GitHub releases and select the actual compatible `workspace-kit-0.5.0.tar.gz` asset and download URL. Keep every component from that bundle. Do not guess asset URLs or substitute another publisher. If no compatible release exists, explain this and offer the explicitly chosen developer source-build route; do not claim ordinary installation succeeded.

Check Python 3.10+ on macOS/Linux. Download and extract outside the project into a temporary directory. Accept only ordinary files and directories; reject absolute paths, traversal, links and special files. A tar data filter does not replace the explicit file-type check. Inspect the installer before running it. Manifest hashes verify content integrity, not publisher identity.

## Install in the current directory

Inspect existing files and instructions. Kit 0.5.0 accepts format 3 only: refuse incompatible research and tools without migration. Substitute actual paths:

```sh
python3 <bundle>/install-workspace.py --kit <bundle> --project <current-directory> --host agents
```

Use `--host claude` for Claude Code. Install all five sibling skills in `.agents/skills/` or `.claude/skills/`, the application under `.workspace`, and only the minimal initial research files. Preserve existing compatible research and instructions, refuse tool conflicts and create stage directories only when needed. Keep the canonical format guide in the shared skill.

A separate research directory is an explicit option, not a default. Before using it, arrange and verify application discovery from that directory; silently placing skills below the conversation directory does not meet installation acceptance.

## Verify application discovery

Read the installed shared skill's `references/agent-adapters.md`. Verify that `research-workspace`, `tunetune-init`, `build-evaluation`, `run-experiments` and `explore` can be found or invoked in the application. Files existing on disk are not this check. Codex normally detects additions automatically; Claude Code may need `/reload-skills` for a new top-level directory. Use current application-supported actions.

If discovery cannot be verified automatically, ask for one concrete skill-picker check. If reopening is required, give the correct directory and a continuation sentence carrying the original request and completed setup. Say plainly, for example: “The files are installed. Please reopen this directory in Codex so the skills appear, then continue with: …”. Do not describe this as a research failure or use terms such as host refresh. Directly reading a skill can recover work but is not proof of list visibility.

Do not claim installation complete and start research until discovery passes. Keep file installation, application discovery and panel availability distinct in the report. Do not promise support for an untested application.

## Open and continue

Start the service in a managed session:

```sh
python3 .workspace/app/workspace.py --project . --port 0 --open
```

Check the actual printed URL responds, then provide a clickable link; do not invent or reuse an unverified port. The panel observes research and only changes project names. An open panel is not a background research scheduler.

Use `research-workspace` and `tunetune-init` to investigate the original goal. The proposal includes a concrete preparation scope and normally one initial decision; explicit delegation can already cover it. After coverage, prepare resources and continue through evaluation and bounded experiments without repeated approval. New data transfers, costs or access outside that scope require a changed decision. End with the actual next action or specific decision, not only missing prerequisites.
