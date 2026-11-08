# Conversation and skill discovery

Use the application's available question capability for a consequential decision; use ordinary conversation when none is available. Offer a recommendation and meaningful choices without forcing a specific tool or requiring the person to have opened the panel. Continue work independent of a pending answer, but do not treat silence as authorization.

Show the panel where the person already looks. When the application has a browser view beside the conversation that you can open, start `workspace.py` without `--open` and open the printed address there yourself; when it only opens links the person clicks, give the address as a link. Use `--open`, which opens the system's default browser, only where the application has no such view. Check the address responds before giving it either way. The side views below were reviewed against application documentation on 2026-11-08; say so if one behaves differently.

## Codex

Use its available interactive user-question tool when suitable; the exact tool depends on the environment and mode. Codex discovers skills in `~/.agents/skills` for the user and `.agents/skills` in the working directory, and through installed plugins; it detects additions automatically, so continue without a skill-picker check. If the person reports them missing, ask them to reopen Codex in that same directory and provide the original request plus a concise continuation sentence. Official guidance: [skills](https://developers.openai.com/codex/skills/).

The Codex app has an in-app browser beside the thread, opened when the person clicks a URL in it, so start the panel without `--open` and give its address as a link, which keeps the panel in Codex instead of a separate browser window. When the Browser plugin is enabled in this thread, open the address in the in-app browser yourself. If the in-app browser cannot load the local address, offer `--open` instead. Official guidance: [in-app browser](https://developers.openai.com/codex/app/browser).

## Claude Code

Claude Code discovers skills in `~/.claude/skills`, `.claude/skills` in the working directory and installed plugins, where they are namespaced such as `tunetune:research-workspace`. Use its interactive question capability when available. A newly created top-level skills directory may require `/reload-skills`; mention it in one sentence and continue by reading the installed skills. Official guidance: [skills](https://code.claude.com/docs/en/skills).

In the Claude desktop app, open the panel's address in its built-in browser pane with the browser tools you have there, starting the panel without `--open`. The terminal version has no side view, so use `--open` there.

## DeepSeek Harness

DeepSeek Harness (`dsh`) discovers skills in `.dsh/skills` and `.agents/skills` at the project root, in `~/.dsh/skills` and `~/.agents/skills`, and through the `dsh-tunetune` plugin, which offers these four skills. The plugin's copies take precedence over same-name copies in the shared `~/.agents/skills`, which were usually installed for another application, but yield to copies in `~/.dsh/skills` or the project's skill folders. Names are not namespaced. It watches those directories, so new skills need no reload.

With the `dsh-tunetune` plugin, the panel delivers the person's answers to this conversation: a decision on the proposal or a round plan, a reference review or acceptance feedback arrives as a message naming the `responses/` record, and a panel that cannot read the records adds a note to your context. For a decision the panel shows, ask in an ordinary message with the attention note set and end your turn, rather than waiting in `ask_user_question`, so an answer from either place starts your next turn. Use `ask_user_question` for other consequential decisions.

With the `dsh-tunetune` plugin installed, do not start `workspace.py` yourself: the plugin runs the study's pinned panel and opens it in the right sidebar once this conversation's folder holds a study, and again when `records.py view` sets a new attention note. Tell them once where it is, in case they close it: Model Lab (模型研究室) in the right sidebar shows this conversation's study, and Model Lab in the left sidebar lists all studies. Studies initialized by tools whose panel predates the plugin open in the browser from there instead. A same-name copy in `~/.dsh/skills` or the project's skill folders replaces the plugin's newer tools for new studies, so when the plugin is installed, do not install the skills there too. Without the plugin, start the panel as INSTALL.md describes.

Commands run in its sandbox, which normally permits writes only inside the workspace. Model downloads, caches outside the project, background runs and network access may need the person's approval; explain why when that happens, prefer locations inside the project when the plan allows, and never work around the sandbox. Discovery reviewed against DeepSeek Harness 0.2.2-rc.1 documentation on 2026-11-07, not yet in a running release.

## Windows through WSL2

The tools need macOS or Linux, because their record protection relies on POSIX file and process primitives, and most fine-tuning libraries work best on Linux anyway. On Windows, run them in WSL2, Microsoft's built-in Linux, which uses the normal Windows NVIDIA driver. If the application itself runs inside WSL, everything below is ordinary Linux. On native Windows, keep the person's actions to approving installation and a possible restart; do everything else yourself.

- **Check.** `wsl.exe -l -q` lists installed distributions; `wsl.exe -d Ubuntu -- python3 --version` confirms Python 3.10+. Ubuntu's default Python qualifies.
- **Install when missing.** Explain in one sentence why Linux is needed and ask before changing the system. Then run `wsl.exe --install -d Ubuntu --no-launch`; Windows asks the person to approve administrator access. If it reports that a restart is required, give them a continuation sentence carrying the original request and ask them to restart and reopen this conversation. If it reports that virtualization is disabled, say that it must be enabled in the computer's firmware settings, which only they can do, and offer to look up the steps for their computer model.
- **Avoid the interactive first launch.** If `wsl.exe -d Ubuntu -- whoami` prints `root`, no default user exists yet: create one as root so the person need not invent a Linux password: `wsl.exe -d Ubuntu -u root -- sh -c "useradd -m -s /bin/bash tunetune && printf '[user]\ndefault=tunetune\n' >> /etc/wsl.conf"`, then `wsl.exe --terminate Ubuntu`. Use `-u root` for later package installs instead of asking for a password.
- **Place the study in Linux.** A Windows folder appears inside WSL under `/mnt/<drive>` with different link, permission and lock behaviour, so `init.py` refuses it. Create the study under the Linux home, such as `~/tunetune/<slug>`, tell the person where it lives, and copy input data from `/mnt/c/...` into it. Your file tools reach it as `\\wsl.localhost\Ubuntu\home\tunetune\tunetune\<slug>`. This replaces initializing the conversation directory: say so once rather than silently.
- **Run commands inside WSL.** Use `wsl.exe -d Ubuntu --cd <study> -- <command>`, with paths as Linux sees them; installed skills are under `/mnt/c/Users/<name>/...`. Install Python packages and download models inside WSL, never into Windows Python.
- **Panel.** Start it inside WSL without `--open` and give the printed address; Windows forwards `127.0.0.1` to WSL, so it opens in the person's normal browser. `explorer.exe "<address>"` from WSL can open it for them.
- **Long runs.** WSL may shut down shortly after its last `wsl.exe` command ends, stopping background processes. Keep a long run attached to a managed session that stays open, and check that it is still alive before reporting progress.
- **GPU.** `nvidia-smi` inside WSL lives in `/usr/lib/wsl/lib/`. If it fails, update the Windows NVIDIA driver rather than installing a Linux driver inside WSL.

WSL guidance is based on Microsoft documentation and has not yet been verified on every Windows release; report anything that differs.

## Installation acceptance

Check that all four skills, `research-workspace`, `tunetune-init`, `build-evaluation` and `run-experiments`, sit side by side where the application discovers them, then continue by reading them. Do not block research on a skill-list check the conversation cannot perform; give reopen instructions only when the application requires them or the person reports the skills missing.

The study lives in the conversation's current directory, initialized there by the shared skill; the skills themselves can live anywhere the application discovers them. For other applications, consult their supported discovery and question mechanisms and report untested compatibility honestly.

Use user-facing instructions such as “If the TuneTune skills do not appear, reopen this directory in Codex and continue with: …”. Avoid internal terms such as host, schema or terminal state unless the person needs technical detail. Discovery behavior reviewed 2026-11-06; verify it in each supported application before making a release claim.
