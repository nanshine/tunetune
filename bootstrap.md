# Start a TuneTune project

This guide is for the Agent receiving a request such as “Use TuneTune to help me build a private model for organizing customer messages, starting in this directory.” Handle setup yourself and continue into tunetune-init. Use the person's language for the conversation.

## Obtain a release

Use the repository supplied by the user; the canonical repository is https://github.com/nanshine/tunetune. Inspect its latest published GitHub release and select the `workspace-kit-<version>.tar.gz` asset from that release. Use the asset's actual download URL, record the release tag, and keep all components from that same bundle. Do not guess a version or substitute a third-party download.

Download to a temporary directory outside the user's project. Extract regular files and directories only, rejecting absolute paths, parent traversal, links, and special files (Python 3.12+ tarfile's data filter can be used together with a regular-file/directory check). Read the bundled installer before executing it. Its manifest verifies file integrity, not publisher identity.

The normal installation needs Python 3.10+ on macOS or Linux. Check the environment yourself. If Python is unavailable, use an available trusted installation mechanism within the host's permissions; explain any unavoidable user action plainly. If no release has been published, report that setup cannot yet use a release. A source build is a developer fallback only when requested, using the README's build instructions.

## Install in the current directory

Inspect existing instructions and files first. Run the extracted installer, substituting the real temporary bundle path and current project directory:

```sh
python3 <bundle>/install-workspace.py --kit <bundle> --project <current-directory> --host agents
```

Use `--host claude` for Claude Code. The default installs sibling skills under `.agents/skills/`; the Claude option uses `.claude/skills/`. Other hosts may read these SKILL.md files directly. Load the installed tunetune-init file immediately if the host does not rediscover skills during the current session. No global skill installation is necessary.

The installer prepares project records, data, src, evaluation, experiments, assessments, releases and supporting directories, plus the prebuilt panel under `.workspace/app/`. It preserves existing files and refuses conflicting tool installations. If AGENTS.md already exists, preserve its guidance and merge the TuneTune entrypoint and contract reference without replacing unrelated instructions. Note the actual skill directory when using a different host.

## Open and continue

Launch the installed service in a managed background session:

```sh
python3 .workspace/app/workspace.py --project . --port 0 --open
```

Read its actual local URL and check it responds before reporting success. `--open` asks the system browser to open the panel; use the host's browser tool or provide a clickable link when necessary. Keep the session available for the user. The panel provides read-only research views and output comparisons, with direct project-name editing as its only write action. Questions, feedback, reviews, and acceptance decisions belong in the Agent client; the Agent performs research and execution.

Continue with the installed tunetune-init skill using the user's original request. Explain what is ready in ordinary language. Model downloads, training environments, and paid resources can wait until the project needs them.
