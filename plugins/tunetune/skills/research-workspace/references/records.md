# Research files

The Agent maintains research files; the panel shows them and records the person's responses. Work starts, stops and changes boundaries in conversation. A project is pinned to the tools that initialized it and continues with them; never migrate or replace them. This is the single format guide.

## Current study

- `project.json`: `{name,language,current_evaluation:null|string,deliveries:[experiment_id]}`. `language` is the language tag of the person's conversation, such as `en` or `zh-CN`; the panel shows its interface in Chinese for `zh` tags and in English otherwise. Write research text for the person in that language, and update the tag when they switch languages.
- `proposal.json`: `{summary,examples:[{id,input,expected_output?}],goal?,output?,considered?:[{family,decision:adopted|excluded,reason}],approaches?:[{id,title,roles:[baseline|recommended|reference|challenge],rationale,limitations?,resource_ids?:[resource_id]}],evaluation?,budget?,stopping?,delivery?,assumptions?:[string],sources?:[{title,url}],feasibility?:{verdict:feasible|conditional|infeasible|unknown,reason}}`. Text fields are plain sentences for a beginner; links belong in `sources`, not in prose.
- `plan.json` (optional until the first round): `{rounds:[{round,goal,budget,items:[{id,title,question,expected,state:planned|running|done|dropped,intervention?,parent?,comparator?,cost?,resource_ids?:[resource_id],note?}],conclusion?}],ideas?:[{title,reason}]}`.
- `resources.json`: `{items:[{id,title,type,status,purpose?,source?,preparation?,access?,path?,location?,version?,size?,monitor?}]}`.

The proposal states direction: goals, requirements and assumptions, the intervention families considered with reasons, recommendation and evidence, alternatives, intended evaluation, finite budget and stopping conditions, and delivery. Approach roles can overlap; complexity is not quality. Resource IDs must exist. Create resources before referencing them in the proposal. Revise it only when the goal, requirements, recommended direction or authorized scope changes. Measurements, run progress and round summaries belong in experiment analyses, never in the proposal. Do not create approval records or revision archives.

The plan records experiment rounds. Rounds are numbered from 1 and appended; a later round never rewrites an earlier one except to update item states, notes and its one-sentence conclusion. Each item reserves the experiment ID it will use, so the panel can show planned work before it exists. `expected` names the observation that would change the next decision; `parent` is intended method ancestry and `comparator` the experiment it must beat. `running` and `done` items require an existing experiment. Dropped items say why in `note`. Results stay in experiment analyses; the plan references IDs only. Ideas not worth a round keep a reason.

Resources are the sole inventory and preparation plan. Types are open text; useful groups include data/annotation, environment, hardware/storage, models, code/tools, services and credentials. `purpose` explains use; `source` identifies origin; `preparation` describes acquisition, estimated download/cache/unpacked space and next check; `access` explains data transfer, fees and credential requirements without secrets. Mark estimates and unknowns honestly. `path` is project-relative and may be a planned destination; `location` identifies an external location. Use at most one. `size` and `version` are strings.

## Responses and panel focus

Decisions are asked and answered in conversation. Where the application delivers panel answers to the conversation, as the DeepSeek Harness plugin does, the panel also offers the decision for a view with an attention note and the Agent receives the answer as a message; elsewhere it only shows what is waiting. Review and acceptance feedback, which are item by item, can always be given in the panel.

`responses/<id>.json` records the person's answer from the panel: `{id,kind:proposal|plan|evaluation_review|acceptance,target:{path,sha256},created_at,decision:approve|revise|continue|stop|submit,note?,items?}`. Review items are `{sample_id,verdict:confirm|correct|question,reference?,note?}`; acceptance items are `{sample_id,experiment_id,verdict:good|bad,note?}`, each naming an output the person read. The target is `proposal.json`, `plan.json`, `evaluation/draft/samples.jsonl` or `comparison/outputs.jsonl` and its hash is the exact bytes shown. Responses are created only by the panel and never edited; the record writer refuses them. A response whose target hash no longer matches answered an older version. For a review, apply confirmed and corrected references to the draft with their `reference_status`, discuss questions, and keep unreviewed items as `draft`. For acceptance feedback, turn each `bad` output with its note into a draft evaluation sample for the person to review; a `good` verdict is evidence about that output, not a reference for other inputs.

`.workspace/view.json` is display state written by `records.py view`: `{revision,open:[view],focus?:{experiment},attention:[{view,message}],updated_at}` with views `proposal|plan|resources|evaluation|review|acceptance`. The panel applies each new revision once and shows attention marks until they are cleared. It is not research evidence.

## Project layout

Everything the study creates stays inside the project, so deleting the directory removes it:

- `resources/`: acquired models, datasets, code and isolated environments, such as `resources/env`.
- `inputs/`: prepared data derived from the person's material and shared by experiments, such as training sets. Evaluation preparation stays under `evaluation/`.
- `evaluation/`, `experiments/` and `comparison/`: measurement, attempts and acceptance outputs described below.
- `.workspace/cache/` and `.workspace/tmp/`: package and model-hub caches, helper scripts and temporary files; neither is research evidence.

Create directories only when needed. Do not add reports, suggestion lists, usage notes or other documents at the root: the panel shows records, and a model's `invoke.json` describes how to call it. Anything kept outside the project, such as a reused global model cache, is a resource with a `location`.

Resource status is `ready|missing|changed|busy|unknown`. Optional `monitor:{kind:file|memory|nvidia_gpu|python,index?:nonnegative_integer}` observes limited facts, not suitability. Runtime observations live in `.workspace/runtime/resources.json` as `{checked_at,items:[{id,state,detail?,size?,modified_at?}]}` and do not overwrite inventory. No record can inject monitor commands.

## Evaluations and source isolation

Prepare optional `evaluation/draft/`, calibrate and check coverage before freezing `evaluation/<version>/`:

- `definition.json`: `{version,description,rubric,metrics:[{id,label,direction:maximize|minimize}],command:[string],no_final_reason?}`.
- `samples.jsonl`: `{sample_id,input,reference?,reference_status?:confirmed|corrected|draft,split?:development|final}` per line; extra task-specific fields are allowed. `confirmed` and `corrected` mean the person reviewed the reference; `draft` means it came from the Agent, a model or unverified metadata.
- Scoring code, explanation of reference origin, coverage, calibration and limitations, necessary display-safe material.
- Generated `manifest.json` listing every ordinary file and its SHA-256, excluding itself.

Unmarked samples are development samples. Freeze refuses a package without development samples, and one without `final` samples unless `no_final_reason` says plainly why there is no final check, such as too little material; the panel shows that reason.

An evaluation measures any candidate through the same contract: its command reads the target from `TUNETUNE_TARGET`, calls that model's entry point and scores the outputs. It never contains candidate-specific prompts, inference or method switches; those belong to the experiment's model. Changed samples or scoring require a new frozen version and appropriate remeasurement. A failed invocation or missing output is not a zero score. An API reference is a measured comparator, not ground truth or a theoretical ceiling. Subjective references need recognizable boundary examples and user calibration where consequential.

Keep source splits and preparation in a subdirectory of `evaluation/`, such as `evaluation/preparation/`, not in new root records or loose files beside the versions. A directory with neither `definition.json` nor `samples.jsonl` is not an evaluation version, even with a manifest pinning it. An optional experiment `data_split:{path,sha256}` pins a JSON file `{train:[{path,sha256}],reserved:[{path,sha256}]}`. Both groups pin local files or verified directories. Declare each training item in config inputs. The verifier checks bytes, disjoint paths/content and exclusion of reserved paths or containing directories from declared experiment inputs. It cannot prove arbitrary code reads only declared inputs. Do not expose protected holdout contents in samples or prompts. Previously inspected examples are not unseen evidence.

## Experiments and model objects

Under `experiments/<id>/`:

- `config.json`: `{id,title,parent_experiment_id:null|string,hypothesis,role?:baseline|candidate|reference,method?,model_name?,framework?,parameters:{},inputs:[{path,sha256}],data_split?:{path,sha256},snapshot_sha256,execution}`.
- `snapshot/`: necessary code/configuration plus generated manifest.
- `status.json`: `{state,updated_at,started_at?,completed_at?,elapsed_seconds?,returncode?,timed_out?,error?,config_sha256?,target?:{kind:local|api,path,sha256},usage?}`.
- `model/`: actual local model or frozen API description and adapter, with an `invoke.json` entry point when it is a directory.
- `analysis.json`: `{outcome:baseline|keep|discard|inconclusive|invalid,summary}`.
- `run.log` and independent `evals/<run-id>/` attempts.

Experiment IDs are `eNNN-short-slug`, such as `e000-keyword` or `e002-embed-lr`, assigned in creation order by `records.py next-id`; the number is how people refer to an experiment and the title explains it. The baseline measured with the evaluation is normally `e000`. Older IDs remain valid.

Parent means method/code ancestry, not inherited weights or ranking. Pin inherited files explicitly. Role is research intent, not measured outcome or delivery eligibility. A rule-based baseline may be useful but does not fulfill an explicit training request.

A model directory exposes `invoke.json`: `{argv:[string],description?,requires?:[{path,sha256}],serve?:{argv:[string],memory_gb?}}`. Run from the project root, it receives an input and an output JSONL path as two extra arguments; input rows are `{sample_id,input}`, output rows `{sample_id,output}`. Evaluations, same-input comparisons and later use call this one entry, so a usable model needs no separate instructions. Validation warns when a delivery lacks one.

`requires` pins files or verified directories outside the model that the entry point reads, normally weights under `resources/` (pin a directory with `records.py manifest`) or a parent experiment's model. Reference shared weights this way instead of copying them into each model, so experiments that change only prompts, parsing or code cost no extra disk. The target hash covers `invoke.json` and therefore these pins; verification, evaluation, comparison and trial runs check each pinned hash. Validation warns when a delivery's required files are missing.

`serve` is an optional resident form of the same model for the panel, worth adding when loading takes long enough to make trials slow. Run from the project root, it loads once, prints `{"ready":true}` on stdout, then answers each stdin line `{sample_id,input}` with one stdout line `{sample_id,output}`, writes logs to stderr and exits at end of input. It must behave exactly like `argv`. `memory_gb` is its peak memory; without it the panel estimates 1.2 times the model and required file sizes. The person loads and unloads models in the acceptance window within a memory budget, half of physical memory by default; nothing is evicted for them, and a run that would exceed the budget asks them to unload first. Resident answers are outputs to read, never measurements.

A target path must be inside this experiment's `model/`. A local file uses its byte hash; a local directory uses its verified manifest hash. For `kind:api`, the path must be a directory with a verified manifest, adapter code and `api.json`:

`{provider,model,request:{},credential_env:[ENV_NAME],limitations,revision?,endpoint?}`.

Record prompt, preprocessing and decoding settings in `request` or pinned adapter/config files. `endpoint` cannot contain credentials, URL query or fragment. Credential names identify inherited environment variables, never values. API keys, authorization headers, passwords and access tokens must not be stored in descriptors, configs, snapshots or logs. The hash proves only local description/adapter integrity, not remote weights. Explain unavailable revision and provider drift in `limitations`. Record actual output and returned model identity when available in task-specific output content.

`usage` is `{requests?,input_tokens?,output_tokens?,cost?,currency?,latency_seconds?}`. Numbers are finite and nonnegative; cost requires currency. Omit unmeasured values rather than recording zero. Process elapsed time remains separate. Publish observed usage while finalizing; never overwrite terminal facts.

## Experiment-local evaluation and comparisons

Under `experiments/<experiment-id>/evals/<run-id>/`:

- `config.json`: `{id,evaluation_version,target_sha256,evaluation_sha256,execution,inputs?:[{path,sha256}]}`.
- `status.json`: process facts above plus optional `metrics:{metric_id:number}` and `usage`; no target field.
- `outputs.jsonl`: `{sample_id,input,output,reference?,scores?}` per sample.
- `run.log`.

Pin the target and whole evaluation manifest. A successful evaluation has every sample's actual output and every declared metric. Inputs/references must match fixed samples. Use fresh IDs for retries or model retests; retraining is unnecessary.

Compare only compatible frozen evaluations, inputs and inference conditions. Keep differing settings visible and do not imply an algorithm-only comparison where prompts, tools or context differ. Reuse measured outputs. Optional `comparison/outputs.jsonl` stores `{sample_id,input,outputs:{experiment_id:JSON_value}}`; missing entries stay missing. This optional same-input view is not proof of compatible scores.

Optional `comparison/inputs.jsonl` holds acceptance inputs `{sample_id,input}`, with extra display fields allowed: real inputs the person wants to see answered, such as proposal examples, new material or all current items. They are read, not scored, and are not unseen evidence. The runner's compare mode calls each named model's entry point on them and merges the outputs; the panel shows each acceptance input beside the selected models' outputs.

Explicit display attachments use `{type:image|audio|video|file,path:project_relative_path}` inside input/output/example content. Only reference material suitable for the user to view. The service serves allowlisted media formats only when explicitly referenced in current display records; no external path or arbitrary project file access. 3D assets are links, not embedded viewers.

## Execution, publication and delivery

`execution:{argv:[string],cwd:string,environment:{name:string},timeout_seconds:positive_number}` uses literal argv, project-relative cwd or `.`, and nonsecret overrides. The runner adds absolute `TUNETUNE_PROJECT`, `TUNETUNE_ATTEMPT` and `TUNETUNE_OUTPUT`: an experiment writes its model to `TUNETUNE_OUTPUT` (`model/`); an evaluation run also receives `TUNETUNE_TARGET`, `TUNETUNE_EVALUATION` and `TUNETUNE_SAMPLES`, the run's own `samples.jsonl` holding only the samples of its split, and writes `outputs.jsonl` rows `{sample_id,output,scores?}`, `metrics.json` and optional `usage.json` to `TUNETUNE_OUTPUT` (`result/`). Score only `TUNETUNE_SAMPLES`; outputs for samples outside the run's split are refused. An evaluation config's optional `split:development|final` defaults to development. A final run publishes only metrics: `finalize` checks that its outputs cover every final sample, then removes them, so no per-sample final result remains to tune against; it refuses a final result holding any other file. The runner refuses a second final run for a model that already has a succeeded final measurement on that evaluation version. After inspecting them, `finalize` publishes these results and marks the attempt succeeded. Credentials may be inherited from the user's configured environment; do not echo them. The runner is not a sandbox, scheduler or permission system.

States are `pending|running|completed|succeeded|failed|cancelled`. `completed` means exit zero awaiting evidence checks. Configs, frozen packages, terminal statuses and measurements are immutable. Retain process facts when finalizing; mutable records use expected-byte SHA-256 and atomic publication. An unfinished directory or a status alone is not success. Respect one writer and count preparation, failures and retests against the same deadline and budget.

Select only verified `local` target experiments, normally with an `invoke.json` entry point, in `project.deliveries`. Keep model files inside their experiments, apart from pinned `requires`, which belong to the delivery and to any export. API targets can be successful references but are not private local deliveries. Selection neither copies nor deploys a model; export separately when requested.

IDs use letters, digits, `_` or `-`. JSON is UTF-8, rejects duplicate keys/nonfinite numbers, and JSONL IDs are unique nonempty strings. Times require timezone-bearing ISO 8601. Paths reject traversal, symlinks and special files. Frozen packages reject hidden files, caches, dependencies and obvious credential files; these checks do not replace inspecting content for secrets. File hashes verify evidence integrity, not scientific validity.
