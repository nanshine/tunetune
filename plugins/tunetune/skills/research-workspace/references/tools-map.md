# Tools by responsibility

Select tools after identifying the experiment, supervision and platform. Verify current official support; do not choose a training architecture merely because a tool was mentioned. Examples reviewed 2026-11-03; they are not frozen recommendations.

| Responsibility | Official starting points | Decision boundary |
|---|---|---|
| General model training | [PyTorch](https://pytorch.org/docs/stable/), [Transformers](https://huggingface.co/docs/transformers/en/training) | Check the actual task, processor and model implementation. |
| Parameter-efficient adaptation | [PEFT](https://huggingface.co/docs/peft/index) | LoRA/QLoRA are resource and parameterization strategies, not task objectives. |
| Language-model post-training | [TRL](https://huggingface.co/docs/trl/index), [verl](https://verl.readthedocs.io/en/latest/start/install.html) | Match the supervision/reward signal; distributed LLM RL is not a universal multimodal recipe. |
| Inference and rollout | [vLLM](https://docs.vllm.ai/), [SGLang](https://docs.sglang.ai/) | These serve inference or rollout; they do not replace the learning objective or trainer. |
| Distributed execution and memory | [Accelerate](https://huggingface.co/docs/accelerate/), [DeepSpeed](https://www.deepspeed.ai/), [Megatron Core](https://docs.nvidia.com/megatron-core/developer-guide/latest/) | Add distributed machinery only when the chosen experiment needs it. |
| Quantization and optimization | [TorchAO](https://docs.pytorch.org/ao/stable/) | Verify training versus inference support and measure quality after conversion. |
| Apple Silicon language models | [MLX-LM](https://github.com/ml-explore/mlx-lm) | Do not assume CUDA dependencies or kernels work on macOS. |
| Domain-specific methods | [Domain guides](technical-map.md) | Use speech, diffusion, graph or reconstruction frameworks for their actual task. |

Pin versions and revisions in experiment inputs. Record preprocessing and decoding as part of the system. Official published results motivate hypotheses, not claims about this study. Prefer a small end-to-end compatibility check before substantial preparation or execution.
