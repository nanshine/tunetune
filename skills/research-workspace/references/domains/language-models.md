# Language model adaptation

First distinguish missing knowledge, output format, domain behavior, preference and reasoning failures. Compare prompting or retrieval with supervised fine-tuning, continued pretraining, preference optimization, reward modeling, verifiable-reward learning and distillation as appropriate. Choose supervision and a trusted evaluation before selecting an optimizer. Parameter-efficient adaptation changes resource needs, not the task objective. Separate reward optimization from independent evaluation and inspect reward hacking, memorization and data contamination.

Official starting points: [Transformers training](https://huggingface.co/docs/transformers/en/training), [TRL](https://huggingface.co/docs/trl/index), [PEFT](https://huggingface.co/docs/peft/index), [verl](https://verl.readthedocs.io/en/latest/start/install.html).

Map reviewed: 2026-11-03. Before execution verify current task support, model license, revision, platform compatibility, data requirements and resource estimates from the selected official sources. These examples are not a compatibility guarantee.
