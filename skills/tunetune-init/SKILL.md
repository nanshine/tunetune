---
name: tunetune-init
description: Start a TuneTune project or clarify an existing project's goal and available resources, especially when someone has an everyday task in mind and little experience training models.
---

# Start with what would be useful

Help someone turn an everyday need into a clear direction they can recognize. A useful starting point may be a few examples and an open proposal; model choice and training strategy can develop as evidence arrives.

## Establish the workspace

Use the current directory unless the user has chosen another. Read existing project instructions and inspect relevant materials before asking questions. For a new workspace, follow [the bootstrap guide](https://github.com/nanshine/tunetune/blob/main/bootstrap.md) to obtain the published bundle and install its tools, panel, templates, and sibling skills. Keep existing project content intact. The user should not need to find a bundle, type commands, or understand installation paths.

Read [research-workspace](../research-workspace/SKILL.md) for the shared record tools and [record contract](../research-workspace/references/records.md) for goal and resource fields. Start the local panel using the installed service, use its actual printed address, and open it with the host's browser tool when available. If opening is unavailable, provide a clickable link. Keep the server in a managed background session and report a startup failure plainly.

The panel provides read-only research views and result comparisons; its only write action is direct editing of the project name. Keep goal/resource additions and all clarification in the Agent client, not panel forms. Research materials and historical feedback remain available for the Agent to read.

## Understand the direction

Start from what the person already said. Ask a small, concrete question in the Agent client that would improve your understanding, then build on the answer. Someone may only know whether an example looks useful; offer examples they can correct rather than asking them to specify a training task.

Inspect relevant files and the available environment. Research candidate models, public datasets, and practical ways to support the task when that would resolve uncertainty. Record sources and what you actually checked. A dataset found online is available to obtain, not ready to use. Download relevant public resources when practical within the task; confirm concrete actions involving payment, private uploads, or substantial downloads when needed.

Keep technical decisions with the Agent unless the user wants to participate. Discuss budget or privacy when an actual choice depends on them, rather than using a mandatory opening questionnaire. Explain discoveries in ordinary language and keep commands and long paths out of the conversation unless needed to resolve a problem.

## Save what you learn

Update goal.json during the conversation: a short summary, optional titled sections, examples with stable IDs, and an optional proposal. Choose sections that help this particular person understand the task. Distinguish their intent from your suggestions. Partial examples are useful; leave unknown input or expected output empty. A proposal describes possibilities and unresolved questions without committing the project to a model or recipe.

When needed, retain decision evidence from the conversation under the shared feedback contract, with its source and the relevant record hashes. Preserve historical answers and distinguish quotations from summaries; do not turn every conversation into a feedback file or treat an opinion as authorization to train, publish, or deploy.

Maintain resources.json with each resource's name, kind, purpose, and observed state. Add source, location, notes, and checked_at when known. Use ready only after checking usability. The panel renders these same records; do not create separate presentation copy.

Use the shared tools to preserve revisions, detect conflicting edits, and validate writes. To guide the panel to the goal or resources, set workspace.json presentation to a new request ID and panel name. Reuse that ID until there is a new reason to guide the view.

## Leave a useful next step

Initialization is complete when the direction is understandable, resource availability is recorded honestly, and the next useful question or action is clear. An empty workspace or a tentative proposal is a valid starting state; a final technical plan is not required.

Summarize the direction and remaining uncertainty in the user's language. If no evaluation exists, suggest working through examples with build-evaluation to establish what useful results look like. Continue when that work is already requested; otherwise invite the user to take that next step. Keep train and review available according to the project's current needs.
