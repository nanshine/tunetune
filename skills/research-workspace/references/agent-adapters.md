# Conversation and skill discovery

Use the application's available question capability for a consequential decision; use ordinary conversation when none is available. Offer a recommendation and meaningful choices without forcing a specific tool or requiring the person to have opened the panel. Continue work independent of a pending answer, but do not treat silence as authorization.

## Codex

Use its available interactive user-question tool when suitable; the exact tool depends on the environment and mode. Install local skills under the current working directory's `.agents/skills`; Codex detects additions automatically, so continue without a skill-picker check. If the person reports them missing, ask them to reopen Codex in that same directory and provide the original request plus a concise continuation sentence. Official guidance: [skills](https://developers.openai.com/codex/skills/).

## Claude Code

Install under the current working directory's `.claude/skills`. Use its interactive question capability when available. A newly created top-level skills directory may require `/reload-skills`; mention it in one sentence and continue by reading the installed skills. Official guidance: [skills](https://code.claude.com/docs/en/skills).

## Installation acceptance

Check that all four skills, `research-workspace`, `tunetune-init`, `build-evaluation` and `run-experiments`, are installed in the application's discovery directory, then continue by reading them. Do not block research on a skill-list check the conversation cannot perform; give reopen instructions only when the application requires them or the person reports the skills missing.

Keep the one-sentence entrypoint in the current directory. An explicitly selected separate directory also requires an application working-directory setup that discovers its skills. For other applications, consult their supported discovery and question mechanisms and report untested compatibility honestly.

Use user-facing instructions such as “If the TuneTune skills do not appear, reopen this directory in Codex and continue with: …”. Avoid internal terms such as host, schema or terminal state unless the person needs technical detail. Discovery behavior reviewed 2026-11-03; verify it in each supported application before making a release claim.
