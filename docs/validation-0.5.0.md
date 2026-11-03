# 0.5.0 implementation and validation

Validated on 2026-11-03. This is a new format-3 kit, not a migration of an existing study.

## Delivered behavior

The five workflows are research-workspace, tunetune-init, build-evaluation, run-experiments and explore. New studies normally have one concrete proposal/resource decision; existing explicit delegation can cover it. Methods are guided by an on-demand technical map, with baselines, recommended improvements and quality references considered independently of complexity.

Format 3 adds approach/resource planning, experiment roles, verified local/API target objects, measured usage and pinned data splits. API target hashes verify descriptions and adapters, never provider weights. Only verified local targets qualify as deliveries. The panel remains read-only except project-name edits, and supports explicit display-safe media and compatible local/API comparisons.

## Verification

- 172 Python tests passed, including temporary loopback services, mocked API execution, inherited credential isolation, API descriptor tampering, incomplete outputs, split overlap, old-format nonmutation, media access and distribution safety.
- 89 frontend tests passed; strict TypeScript and production Vite build passed.
- All five skill frontmatters passed skill-creator validation; packaged local documentation links resolve.
- Independent Agent exercises used temporary image/text/audio study materials. A separate evaluator executed real synthetic offline audio baseline and improvement runs through the record/runner path. No private uploads, external downloads or paid API calls were used. These checks establish workflow behavior, not real task quality.
- The actual kit was built into a fresh output directory, then into dist; its installer ran twice against a temporary study, preserving files and reporting zero additions the second time. The standalone synthetic demo exercises local models, reevaluation and comparisons.
- Browser inspection covered narrow and desktop layouts, proposal, canvas controls and same-input comparison. Screenshots are local development assets under design/validation-0.5.0 and are excluded from kits.

## Boundaries still requiring external acceptance

Codex and Claude Code skill-list visibility in a newly installed interactive session has not been directly verified here. File publication, CLI continuations and package integrity are tested; they are not evidence of application discovery. Follow the installed agent-adapters guide to verify the five names before claiming setup is complete. No Release was published.

Public resource acquisition is tested with local/mocked sources, not live large downloads. Git byte limits constrain extracted content, not wire traffic or internal object storage; cross-filesystem atomic publication safely fails. Actual model licensing, platform support, memory, quality and service cost need task-specific verification. Arbitrary executed code is not sandboxed by these helpers, and credential-log discipline cannot be guaranteed for arbitrary child programs.
