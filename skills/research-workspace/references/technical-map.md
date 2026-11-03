# Research technical map

Use this map when selecting or revisiting an approach. Locate the task by useful input/output behavior, available supervision, data scale and resource boundaries. Read only relevant domain guides, then verify current official documentation and model cards. This is a search starting point, not an approved-model list; external investigation is normal, not a last resort.

Consider a credible cheap baseline, the best-supported feasible route and a strong quality reference or challenge. These are roles, not complexity levels or mandatory separate runs. Explain when a role coincides with another or cannot run. Compare real behavior under compatible measurement; a reference model is not a theoretical ceiling or its own ground truth.

| Task family | Guide |
|---|---|
| Tables, classification, regression, anomaly detection | [Tabular](domains/tabular.md) |
| Forecasting and temporal signals | [Time series](domains/time-series.md) |
| Text classification, retrieval and ranking | [Text](domains/text.md) |
| Language generation and behavior adaptation | [Language models](domains/language-models.md) |
| Image classification, detection and segmentation | [Vision](domains/vision.md) |
| Image synthesis and editing | [Image generation](domains/image-generation.md) |
| Speech recognition, synthesis and audio | [Audio](domains/audio.md) |
| Video understanding and generation | [Video](domains/video.md) |
| Documents, vision-language and cross-modal tasks | [Multimodal](domains/multimodal.md) |
| Graphs, point clouds, reconstruction and 3D generation | [Graphs and spatial](domains/spatial.md) |

Use the [tool index](tools-map.md) to distinguish algorithms, training frameworks, inference engines and hardware requirements. Use [resource planning](resource-planning.md) to turn a route into an explicit preparation scope. At execution, pin chosen revisions and actual inputs in experiment records rather than adding project-specific recipes here.
