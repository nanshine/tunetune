# Install TuneTune and start a study

Install the four skills, initialize the current conversation directory, open the panel and continue with the person's original request in their language. Do not silently create a child study directory.

## Install the skills

Use the user-supplied repository, normally https://github.com/nanshine/tunetune; do not substitute another publisher. Skip this step when `research-workspace`, `tunetune-init`, `build-evaluation` and `run-experiments` are already installed side by side.

With Node.js available, install for the current application only, user-wide so later studies in other directories need nothing new. Use that application's skills CLI identifier, such as `codex`, `claude-code`, `cursor`, `opencode`, `trae`, `trae-cn`, `qoder` or `qoder-cn`:

```sh
npx skills add nanshine/tunetune --global --agent <application> -y
```

Do not use `--agent '*'` on the person's behalf, since it writes into every supported application. Without Node.js, or when the skills CLI does not know the application, clone into a temporary directory outside the project and copy the four folders under `plugins/tunetune/skills/` into the application's user skill directory: `~/.claude/skills/` for Claude Code, `~/.agents/skills/` for Codex, `~/.cursor/skills/` for Cursor, `~/.config/opencode/skills/` for OpenCode, `~/.trae/skills/` or `~/.trae-cn/skills/` for Trae, `~/.qoder/skills/` or `~/.qoder-cn/skills/` for Qoder. For any other application, use the user skill directory its documentation names, and say that TuneTune has not been tested there. Accept only ordinary files and directories. Refuse to replace existing skill folders that differ, and tell the person instead: their research may be pinned to those tools.

Plugins work too and need no Node.js: in Claude Code, `/plugin marketplace add nanshine/tunetune` then `/plugin install tunetune@tunetune`; in Codex, `codex plugin marketplace add nanshine/tunetune` then `codex plugin add tunetune@tunetune`. Leave the choice of plugin to the person.

## Initialize the current directory

Check Python 3.10+ on macOS/Linux. Read the installed shared skill's `references/agent-adapters.md`, then run its initializer with actual paths:

```sh
python3 <research-workspace skill>/scripts/init.py --project <current-directory>
```

It verifies the skill's manifest, adds only the missing project guide, minimal research files and pinned tools under `.workspace/app/`, and preserves existing compatible research and instructions. It refuses older research formats and projects pinned to other tools without migrating them; explain that plainly instead of working around it.

## Open and continue

Start the panel in a managed session and give the actual printed address once it responds:

```sh
python3 .workspace/app/workspace.py --project . --port 0 --open
```

Continue in this conversation by reading the installed skills; do not ask the person to inspect a skill picker. Mention a refresh only when the application documents one, such as `/reload-skills` in Claude Code for a new top-level skills directory, or when the person reports the skills missing, with a continuation sentence carrying the original request. Report installation in a sentence, then use `research-workspace` and `tunetune-init` to investigate the goal. An open panel is not a background research scheduler.
