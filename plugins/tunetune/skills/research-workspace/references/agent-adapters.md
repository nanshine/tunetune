# Conversation and skill discovery

Use the application's available question capability for a consequential decision; use ordinary conversation when none is available. Offer a recommendation and meaningful choices without forcing a specific tool or requiring the person to have opened the panel. Continue work independent of a pending answer, but do not treat silence as authorization.

## Codex

Use its available interactive user-question tool when suitable; the exact tool depends on the environment and mode. Codex discovers skills in `~/.agents/skills` for the user and `.agents/skills` in the working directory, and through installed plugins; it detects additions automatically, so continue without a skill-picker check. If the person reports them missing, ask them to reopen Codex in that same directory and provide the original request plus a concise continuation sentence. Official guidance: [skills](https://developers.openai.com/codex/skills/).

## Claude Code

Claude Code discovers skills in `~/.claude/skills`, `.claude/skills` in the working directory and installed plugins, where they are namespaced such as `tunetune:research-workspace`. Use its interactive question capability when available. A newly created top-level skills directory may require `/reload-skills`; mention it in one sentence and continue by reading the installed skills. Official guidance: [skills](https://code.claude.com/docs/en/skills).

## DeepSeek Harness

DeepSeek Harness (`dsh`) discovers skills in `.dsh/skills` and `.agents/skills` at the project root, in `~/.dsh/skills` and `~/.agents/skills`, and through the `dsh-tunetune` plugin, which offers these four skills; a same-name copy the person installed in a skill directory takes precedence over the plugin's. Names are not namespaced. It watches those directories, so new skills need no reload. Use its `ask_user_question` tool for consequential decisions when available.

With the `dsh-tunetune` plugin installed, do not start `workspace.py` yourself: the plugin runs the study's pinned panel when the person opens it. Tell them once where it is: the TuneTune card on the right sidebar's guide page shows this conversation's study beside it, and TuneTune in the left sidebar lists all studies. Studies initialized by tools whose panel predates the plugin show the standalone command instead. Without the plugin, start the panel as INSTALL.md describes.

Commands run in its sandbox, which normally permits writes only inside the workspace. Model downloads, caches outside the project, background runs and network access may need the person's approval; explain why when that happens, prefer locations inside the project when the plan allows, and never work around the sandbox. Discovery reviewed against DeepSeek Harness 0.2.2-rc.1 documentation on 2026-11-07, not yet in a running release.

## Installation acceptance

Check that all four skills, `research-workspace`, `tunetune-init`, `build-evaluation` and `run-experiments`, sit side by side where the application discovers them, then continue by reading them. Do not block research on a skill-list check the conversation cannot perform; give reopen instructions only when the application requires them or the person reports the skills missing.

The study lives in the conversation's current directory, initialized there by the shared skill; the skills themselves can live anywhere the application discovers them. For other applications, consult their supported discovery and question mechanisms and report untested compatibility honestly.

Use user-facing instructions such as “If the TuneTune skills do not appear, reopen this directory in Codex and continue with: …”. Avoid internal terms such as host, schema or terminal state unless the person needs technical detail. Discovery behavior reviewed 2026-11-06; verify it in each supported application before making a release claim.
