# Text, retrieval and ranking

Compare lexical features with pretrained semantic encoders and task-specific adaptation. For classification consider frozen embeddings plus a head, SetFit or encoder fine-tuning; for retrieval distinguish candidate recall from reranking quality. A strong language-model reference can reveal semantic headroom, but confirm labels and subjective disagreements independently. Investigate long-input truncation, multilingual ability, document grouping and deployment cost before choosing a model.

Official starting points: [Sentence Transformers](https://www.sbert.net/docs/quickstart.html), [Cross-encoders](https://www.sbert.net/docs/cross_encoder/training_overview.html), [SetFit](https://huggingface.co/docs/setfit/conceptual_guides/setfit).

Map reviewed: 2026-11-03. Before execution verify current task support, model license, revision, platform compatibility, data requirements and resource estimates from the selected official sources. These examples are not a compatibility guarantee.
