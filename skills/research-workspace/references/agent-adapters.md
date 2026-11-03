# Conversation and skill discovery

Use the application's available question capability for a consequential decision; use ordinary conversation when none is available. Offer a recommendation and meaningful choices without forcing a specific tool or requiring the person to have opened the panel. Continue work independent of a pending answer, but do not treat silence as authorization.

## Codex

Use its available interactive user-question tool when suitable; the exact tool depends on the environment and mode. Install local skills under the current working directory's `.agents/skills`. Verify that all five TuneTune skills can be found or invoked through Codex, not merely that files exist. Codex detects additions automatically; if they do not appear, ask the person to reopen Codex in that same directory and provide the original request plus a concise continuation sentence. Official guidance: [skills](https://developers.openai.com/codex/skills/).

## Claude Code

Install under the current working directory's `.claude/skills`. Use its interactive question capability when available. A newly created top-level skills directory may require `/reload-skills`; verify the five names can be found or invoked. Official guidance: [skills](https://code.claude.com/docs/en/skills).

## Installation acceptance

Check `research-workspace`, `tunetune-init`, `build-evaluation`, `run-experiments` and `explore`. File publication and application discovery are separate checks. If the application exposes no discovery interface, request a concrete check in its skill picker; do not claim visibility based on a filesystem listing. Reading `SKILL.md` can recover work but does not prove installation discovery.

Keep the one-sentence entrypoint in the current directory. An explicitly selected separate directory also requires a verified application working-directory/discovery setup. For other applications, consult their supported discovery and question mechanisms and report untested compatibility honestly.

Use user-facing instructions such as “The files are installed. Please reopen this directory in Codex so the skills appear, then continue with: …”. Avoid internal terms such as host, schema or terminal state unless the person needs technical detail. Discovery behavior reviewed 2026-11-03; verify it in each supported application before making a release claim.
