# Research files — format 3

The Agent maintains research files; the panel observes them. Decisions and authorization stay in conversation. Kit 0.5.0 supports format 3 only: refuse older projects and tools without migration or replacement. This is the single format guide.

## Current study

- `project.json`: `{schema_version:3,name,language,current_evaluation:null|string,deliveries:[experiment_id]}`.
- `proposal.json`: `{summary,sections:[{title,body}],examples:[{id,input,expected_output?}],approaches?:[{id,title,roles:[baseline|recommended|reference|challenge],rationale,limitations?,resource_ids?:[resource_id]}],feasibility?:{verdict:feasible|conditional|infeasible|unknown,reason}}`.
- `resources.json`: `{items:[{id,title,type,status,purpose?,source?,preparation?,access?,path?,location?,version?,size?,monitor?}]}`.

Keep prose coherent: goals, assumptions, recommendation and evidence, alternatives, evaluation, finite budget and stopping conditions, delivery and next validation. Approach roles can overlap; complexity is not quality. Resource IDs must exist. Create resources before referencing them in the proposal. Update the current proposal when understanding or evidence changes; do not create approval records or revision archives.

Resources are the sole inventory and preparation plan. Types are open text; useful groups include data/annotation, environment, hardware/storage, models, code/tools, services and credentials. `purpose` explains use; `source` identifies origin; `preparation` describes acquisition, estimated download/cache/unpacked space and next check; `access` explains data transfer, fees and credential requirements without secrets. Mark estimates and unknowns honestly. `path` is project-relative and may be a planned destination; `location` identifies an external location. Use at most one. `size` and `version` are strings.

Status is `ready|missing|changed|busy|unknown`. Optional `monitor:{kind:file|memory|nvidia_gpu|python,index?:nonnegative_integer}` observes limited facts, not suitability. Runtime observations live in `.workspace/runtime/resources.json` as `{checked_at,items:[{id,state,detail?,size?,modified_at?}]}` and do not overwrite inventory. No record can inject monitor commands.

## Evaluations and source isolation

Prepare optional `evaluation/draft/`, calibrate and check coverage before freezing `evaluation/<version>/`:

- `definition.json`: `{version,description,rubric,metrics:[{id,label,direction:maximize|minimize}],command:[string]}`.
- `samples.jsonl`: `{sample_id,input,reference?}` per line; extra task-specific fields are allowed.
- Scoring and inference code, explanation of reference origin, coverage, calibration and limitations, necessary display-safe material.
- Generated `manifest.json` listing every ordinary file and its SHA-256, excluding itself.

Changed samples or scoring require a new frozen version and appropriate remeasurement. A failed invocation or missing output is not a zero score. An API reference is a measured comparator, not ground truth or a theoretical ceiling. Subjective references need recognizable boundary examples and user calibration where consequential.

Keep source splits and preparation under `evaluation/`, not new root records. An optional experiment `data_split:{path,sha256}` pins a JSON file `{train:[{path,sha256}],reserved:[{path,sha256}]}`. Both groups pin local files or verified directories. Declare each training item in config inputs. The verifier checks bytes, disjoint paths/content and exclusion of reserved paths or containing directories from declared experiment inputs. It cannot prove arbitrary code reads only declared inputs. Do not expose protected holdout contents in samples or prompts. Previously inspected examples are not unseen evidence.

## Experiments and model objects

Under `experiments/<id>/`:

- `config.json`: `{id,title,parent_experiment_id:null|string,hypothesis,role?:baseline|candidate|reference,method?,model_name?,framework?,parameters:{},inputs:[{path,sha256}],data_split?:{path,sha256},snapshot_sha256,execution}`.
- `snapshot/`: necessary code/configuration plus generated manifest.
- `status.json`: `{state,updated_at,started_at?,completed_at?,elapsed_seconds?,returncode?,timed_out?,error?,config_sha256?,target?:{kind:local|api,path,sha256},usage?}`.
- `model/`: actual local model or frozen API description and adapter.
- `analysis.json`: `{outcome:baseline|keep|discard|inconclusive|invalid,summary}`.
- `run.log` and independent `evals/<run-id>/` attempts.

Parent means method/code ancestry, not inherited weights or ranking. Pin inherited files explicitly. Role is research intent, not measured outcome or delivery eligibility. A rule-based baseline may be useful but does not fulfill an explicit training request.

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

Explicit display attachments use `{type:image|audio|video|file,path:project_relative_path}` inside input/output/example content. Only reference material suitable for the user to view. The service serves allowlisted media formats only when explicitly referenced in current display records; no external path or arbitrary project file access. 3D assets are links, not embedded viewers.

## Execution, publication and delivery

`execution:{argv:[string],cwd:string,environment:{name:string},timeout_seconds:positive_number}` uses literal argv, project-relative cwd or `.`, and nonsecret overrides. Credentials may be inherited from the user's configured environment; do not echo them. The runner is not a sandbox, scheduler or permission system.

States are `pending|running|completed|succeeded|failed|cancelled`. `completed` means exit zero awaiting evidence checks. Configs, frozen packages, terminal statuses and measurements are immutable. Retain process facts when finalizing; mutable records use expected-byte SHA-256 and atomic publication. An unfinished directory or a status alone is not success. Respect one writer and count preparation, failures and retests against the same deadline and budget.

Select only verified `local` target experiments in `project.deliveries`. Keep files inside their experiments. API targets can be successful references but are not private local deliveries. Selection neither copies nor deploys a model; export separately when requested.

IDs use letters, digits, `_` or `-`. JSON is UTF-8, rejects duplicate keys/nonfinite numbers, and JSONL IDs are unique nonempty strings. Times require timezone-bearing ISO 8601. Paths reject traversal, symlinks and special files. Frozen packages reject hidden files, caches, dependencies and obvious credential files; these checks do not replace inspecting content for secrets. File hashes verify evidence integrity, not scientific validity.
