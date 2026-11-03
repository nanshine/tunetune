# Research files — format 2

Project files describe the study; the panel reads them. Keep one current proposal, experiment-local evidence and a small list of chosen models. Format 2 is an explicit format change, not an automatic migration. This guide lives in the shared skill, not as another file in each project.

## Project

- `project.json`: `{schema_version:2,name,language,current_evaluation:null|string,deliveries:[experiment_id]}`.
- `proposal.json`: `{summary,sections:[{title,body}],examples:[{id,input,expected_output?}],feasibility?:{verdict:feasible|conditional|infeasible|unknown,reason}}`.
- `resources.json`: `{items:[{id,title,type,status,path?,location?,version?,size?,monitor?}]}`.

Proposal edits replace the current account with conflict detection. Discuss proposals and consequential choices in conversation, without recording confirmations or revisions. Each experiment's hypothesis explains why it was made. Exploration suggestions stay in conversation or the relevant experiment's analysis.

Resource type is an Agent-chosen group. Status is `ready`, `missing`, `changed`, `busy` or `unknown`. Path, version and size are optional strings. `path` is project-relative; `location` is an explicit external location, not a command. Use at most one. `monitor` is optional `{kind:file|memory|nvidia_gpu|python,index?:nonnegative_integer}`. File probes observe existence, size and modification metadata, not training suitability. Unsupported or stale probes are unknown.

The local service periodically writes `.workspace/runtime/resources.json`: `{checked_at,items:[{id,state,detail?,size?,modified_at?}]}`. The API exposes this as `observations` beside its file snapshot. Observations do not overwrite inventory. Probe kinds are fixed; records cannot inject commands or network requests.

## Evaluation standard

Prepare optional `evaluation/draft/`, then freeze `evaluation/<version>/` containing:

- `definition.json`: `{version,description,rubric,metrics:[{id,label,direction:maximize|minimize}],command:[string]}`.
- `samples.jsonl`: rows `{sample_id,input,reference?}`. Input/reference may be structured JSON; extra task-specific sample fields are allowed.
- Scoring/inference code and required local material.
- Generated `manifest.json` listing actual file byte hashes.

The fixed samples filename is also the panel's data source. Include only material suitable for the user to view. Keep large/protected data elsewhere and pin additional inputs in execution config. Important data limitations belong in research text, not mandatory UI metadata.

Calibrate the actual scoring path. Changed scoring or samples require a new version and appropriate remeasurement. Separate development examples from independent final checks; exposed examples are not unseen evidence.

## Experiment

Under `experiments/<id>/`:

- `config.json`: `{id,title,parent_experiment_id:null|string,hypothesis,method?,model_name?,framework?,parameters:{},inputs:[{path,sha256}],snapshot_sha256,execution}`.
- `status.json`: `{state,updated_at,started_at?,completed_at?,elapsed_seconds?,returncode?,timed_out?,error?,config_sha256?,model_path?,model_sha256?}`.
- `analysis.json`: `{outcome:baseline|keep|discard|inconclusive|invalid,summary}`.
- `snapshot/`: necessary code/configuration and generated manifest.
- `model/`: actual model files, identified by status.
- `run.log`: one combined execution log.
- `evals/<run-id>/`: independent evaluation attempts.

Parent identifies method/code ancestry, not necessarily inherited weights or the comparator. Pin inherited files in inputs. Hypothesis and analysis identify important comparison evidence. Revise analysis in place with conflict detection; preserve measurements rather than archiving interpretations.

`model_path` is project-relative inside this experiment's `model/`. A file uses its byte SHA-256; a directory uses its generated manifest SHA-256 with verified contents. A successful experiment identifies a verified usable model. A fixed-rule baseline need not pretend to be trained.

## Experiment-local evaluations

Under `experiments/<experiment-id>/evals/<run-id>/`:

- `config.json`: `{id,evaluation_version,model_sha256,evaluation_sha256,execution,inputs?:[{path,sha256}]}`. The parent directory identifies the experiment. `evaluation_sha256` pins the entire evaluation manifest.
- `status.json`: the same process fields as above, plus `metrics?:{metric_id:finite_number}`.
- `outputs.jsonl`: rows `{sample_id,input,output,reference?,scores?}`.
- `run.log`: one combined log.

Repeated evaluations use fresh IDs, without retraining or replacing results. Compare only compatible versions and inference/data conditions. A successful evaluation needs actual outputs and declared metrics.

## Execution and publication

`execution` is `{argv:[string],cwd:string,environment:{name:string},timeout_seconds:positive_finite_number}`. Use literal argv, project-relative cwd (or `.`), nonsecret environment overrides and finite timeout. Verify frozen code and declared input hashes. Checks are not a sandbox or authorization engine.

States are `pending`, `running`, `completed`, `succeeded`, `failed`, `cancelled`. Completed means exit zero awaiting output verification. The runner reserves `run.log`, executes the config and writes process facts directly into status. Clean up only the invocation's own process group on completion/timeout. Existing logs or started states block another execution of that ID.

Inspect outputs before finalizing success, preserving recorded process facts. Final states and measurements are immutable. Configs, frozen packages and terminal facts cannot be replaced; retry under a fresh ID. Mutable records use expected-byte hashes and atomic writes. Reject unsafe paths, symlinks and special files. Multi-file publication is not a transaction; incomplete records are not success. A status alone does not prove a live process.

Keep only needed snapshots, not unrelated code, caches or private inputs. Manifests list every ordinary file except themselves; verify contents, not just manifest presence. IDs contain letters, digits, underscore or hyphen. JSON is UTF-8, rejects duplicate keys and nonfinite numbers; JSONL rows have unique nonempty sample IDs. Times use timezone-bearing ISO 8601. Paths are project-relative without traversal; explicit external locations are not automatically read.

## Comparison and delivery

Project deliveries list chosen experiment IDs. Verified models stay in experiments; selection does not copy, deploy or prove user satisfaction. Export a standalone bundle only when requested.

For extra same-input comparisons, save `comparison/outputs.jsonl`: `{sample_id,input,outputs:{experiment_id:text}}`. Missing outputs stay missing. Update atomically with conflict detection. A single optional `comparison/run.log` holds generation diagnostics. Reuse suitable existing evaluation outputs instead of copying evidence.

Requests and decisions stay in conversation. Clear authorization can span skills and bounded rounds; ask only for missing consequential decisions or changed boundaries. Count failures, retests and remaining final-validation time. The panel observes research rather than supplying another execution or annotation interface.
