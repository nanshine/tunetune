# Deterministic research tools

Use Python 3.10+ on POSIX macOS/Linux; no additional packages. Resolve the installed shared skill's absolute path. `$RECORDS` below is its `scripts/records.py`, `$RUN` is the sibling `scripts/run.py`, and `$PROJECT` is the absolute research-project directory. Read [records.md](records.md) for format 2. Incompatible project schemas are rejected, not migrated.

## Inspect and validate

```sh
python3 "$RECORDS" hash --project "$PROJECT" --path proposal.json
python3 "$RECORDS" validate --project "$PROJECT"
```

`hash` returns `{path,sha256}` for actual file bytes. `validate` returns `{valid,errors,warnings,unfinished}`. Validation checks core records, record shapes, references, frozen file sets and byte hashes, model containment, declared metrics and evaluation samples/outputs. Missing or nonfinal attempt statuses are unfinished; `completed` still awaits output verification. Missing installed-tool metadata is a warning; an incompatible schema range is an error.

Exit 0 means no validation errors, not scientific validity or finished research. Errors exit 1; argument errors exit 2. Results are JSON on stdout; operational errors are JSON on stderr. Validation is read-only and can observe partial multi-file publication. It does not prove process liveness, dependency completeness, suitability of resources or user authorization. Explicit external resource locations are descriptive and never fetched.

## Publish records

Prepare a complete UTF-8 input file, then publish it:

```sh
python3 "$RECORDS" write --project "$PROJECT" --path experiments/e1/config.json --input /absolute/config.json --create
python3 "$RECORDS" write --project "$PROJECT" --path proposal.json --input /absolute/proposal.json --expected-sha256 "$PREVIOUS_SHA256"
python3 "$RECORDS" write --project "$PROJECT" --path experiments/e1/analysis.json --input /absolute/analysis.json --create
```

Choose exactly one of `--create` or `--expected-sha256`. Returns `{path,sha256}`. Creation never overwrites. Updates compare existing bytes under the writer lock. Mutable records are project, proposal, resources, experiment analysis, comparison outputs, evaluation drafts and nonfinal status. Updates replace current records without retaining earlier interpretations. Configs, published evaluation files, evaluation outputs and final statuses are immutable.

Publication checks references before writing: freeze snapshots before experiment configs, publish a verified successful model before evaluation configs or delivery selection, and publish evaluation outputs before success. A successful evaluation includes every fixed sample and all declared metrics. Output inputs and any supplied references must match those samples; score IDs must be declared. Comparison outputs map existing experiment IDs to strings; missing entries remain missing.

Status updates cannot move backwards or remove/change recorded process facts, model identifiers or measurements. To finalize, read the latest status, retain all its fields, update `state` and `updated_at`, add verified model fields or metrics, then write with its current byte hash. An exit-zero `completed` status is not success. Failed and cancelled statuses cannot be revised; use a fresh attempt ID.

The writer lock is `.workspace/runtime/records.lock`. Contention fails immediately. A persistent lock file is normal; never delete or steal it. Directory-descriptor access rejects traversal, symlinks and special files. Atomic file replacement is not a multi-file transaction. Direct editors and child programs can bypass the cooperating-writer lock; coordinate them and validate before dependent actions. The record writer does not edit arbitrary source files or logs.

## Freeze code and evaluation packages

```sh
python3 "$RECORDS" freeze --project "$PROJECT" --source /absolute/prepared-code --path experiments/e1/snapshot
python3 "$RECORDS" freeze --project "$PROJECT" --source /absolute/prepared-evaluation --path evaluation/v1
```

Returns `{path,files,manifest_sha256}`. Store the snapshot hash in experiment `snapshot_sha256`; store the evaluation hash in each evaluation run's `evaluation_sha256`. The latter pins the entire manifest, not just the definition.

Source must be a nonempty ordinary file tree without a root `manifest.json`, symlinks or special files, and must not overlap the destination. Evaluation sources require `definition.json` matching the destination version and valid `samples.jsonl`; include scoring code and required local material. The destination must not exist. Files are created exclusively and the manifest is written last. An interrupted directory cannot be reused. Freeze does not select the current evaluation or start a command.

Executable bits are retained without special permissions. Files are buffered in memory: use freeze for modest code/evaluation packages, not large data or model copies. Coordinate the source writer; this is not a transactionally consistent capture of changing files or an OS read-only guarantee.

## Identify a model

Keep model files inside `experiments/<id>/model/`. For a single model file, use `hash` and put its project-relative path and byte hash in experiment status as `model_path` and `model_sha256`.

For a model directory already generated by the command:

```sh
python3 "$RECORDS" manifest --project "$PROJECT" --path experiments/e1/model
```

This writes one exclusive `manifest.json` in place and returns `{path,files,manifest_sha256}`. It also accepts a subdirectory inside that experiment's `model/`. Use the directory as `model_path` and the returned manifest hash as `model_sha256`. Every ordinary file except the manifest itself is listed; verification checks both bytes and exact membership. Coordinate the producer before generating it, before terminal status. Existing manifests and already-frozen parent packages cannot be changed. Select verified successful experiment IDs in `project.deliveries`; selection neither copies nor deploys models.

## Execute one prepared attempt

```sh
python3 "$RUN" --project "$PROJECT" --path experiments/e1
python3 "$RUN" --project "$PROJECT" --path experiments/e1/evals/r1
```

The immutable config supplies `execution:{argv,cwd,environment,timeout_seconds}`. Use a literal nonempty argv array, `.` or a project-relative directory, string-valued nonsecret environment overrides and a positive finite timeout. No command, environment, timeout or retry overrides are accepted. Environment overrides overlay the inherited environment; this is not hermetic execution.

Preflight verifies the snapshot and ancestry for experiments, or the successful parent model and full evaluation package for evaluation runs. Every declared `inputs:[{path,sha256}]` reference is checked: files use byte hashes; directories require matching, fully verified manifests. Additional inputs are optional only for evaluation runs. External inputs must first become local pinned material. These checks cannot prove that argv uses only declared dependencies; prepare honest configs and retain necessary code/material.

The runner holds the shared lock through execution and status publication. Child commands must not call `records.py write`; write model files or task-specific staging outputs directly instead. No automatic metric extraction is assumed. Do not modify the immutable config or frozen packages from the child.

An existing `run.log`, output file, model files or started/final status blocks execution. Only absent status or `pending` without process/output facts may start. The exclusively created `run.log` permanently reserves the attempt, even empty after a crash. Stdout and stderr share that log; stdin is closed. A descriptor-pinned cwd prevents path replacement from redirecting startup.

The runner writes `running`, then `completed` for exit zero or `failed` for nonzero exit, timeout, launch failure or handled interruption. It returns the saved status, including `started_at`, `completed_at`, `elapsed_seconds`, `returncode`, `timed_out`, `config_sha256` and optional `error`. The process code comes from a private supervisor pipe, never stdout. When no payload result is available, the code is the supervisor cleanup signal or null if spawning failed. Elapsed time uses a monotonic clock and includes cleanup. CLI exit 0 means process completion only; failed execution exits 1.

Inspect outputs after the lock is released. Publish verified model identifiers or evaluation outputs/metrics and finalize status explicitly, preserving all process facts. Repeated evaluations use new nested IDs without retraining. Never reset status or delete a reserved log to rerun an ID.

The supervisor reserves its process-group identity until cleanup. Completion, timeout and handled CLI SIGINT/SIGTERM kill only this invocation's group, including workers left after payload exit. Commands must not detach or daemonize. Escaped processes, hard-killed runners, power loss, arbitrary filesystem writes, log size and global spending are not contained. These tools are not a sandbox, scheduler or authorization engine. Python embedders own their host's signal lifecycle; use the CLI subprocess when managed cancellation is needed.

## Python API

- `Tree(root)`: close with `tree.close()` in `finally`. Roots and source paths must not traverse symlinks.
- `digest(bytes)`, `encoded(value)`, `strict(bytes_or_text)`, `shape(path,bytes)`, `read_record(tree,path)`.
- `write(tree,path,source,create=False,expected=None) -> {path,sha256}`.
- `freeze(tree,root,source,path)` and `manifest(tree,path) -> {path,files,manifest_sha256}`.
- `verify_hash(tree,path,expected)`, `verify_manifest(tree,base,expected=None)`, `verify_path_hash(tree,path,expected)`, `verify_inputs(tree,attempt_path,config)`.
- `validate(tree) -> {valid,errors,warnings,unfinished}`.
- Sibling `run.py`: `execute(tree,attempt_path) -> status`.

Writing, freezing, manifest generation and execution acquire the lock themselves; do not call them while holding `tree.locked()`. Rejected operations raise errors. Neither tool imports or controls the panel.
