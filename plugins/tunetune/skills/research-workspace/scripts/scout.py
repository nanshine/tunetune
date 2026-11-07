#!/usr/bin/env python3
"""Read-only lookup of public models (Hugging Face or ModelScope), datasets, papers and repositories, plus hardware fit estimates.

Results are leads for research decisions, not evidence about this study. Nothing is downloaded or
written; no credentials are read or accepted.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

HF = os.environ.get("TUNETUNE_SCOUT_HF", "https://huggingface.co")
MODELSCOPE = os.environ.get("TUNETUNE_SCOUT_MODELSCOPE", "https://www.modelscope.cn")
ARXIV = os.environ.get("TUNETUNE_SCOUT_ARXIV", "https://export.arxiv.org")
GITHUB = os.environ.get("TUNETUNE_SCOUT_GITHUB", "https://api.github.com")
MAX_BYTES = 8 * 1024 * 1024
PERMISSIVE = {"mit", "apache-2.0", "bsd", "bsd-2-clause", "bsd-3-clause", "isc", "cc-by-4.0", "cc0-1.0", "unlicense"}
COPYLEFT = {"gpl-2.0", "gpl-3.0", "lgpl-2.1", "lgpl-3.0", "agpl-3.0", "mpl-2.0", "cc-by-sa-4.0"}
BYTES_PER_PARAM = {"fp32": 4.0, "fp16": 2.0, "bf16": 2.0, "int8": 1.0, "q4": 0.6}
USABLE_SHARE = {"apple": 0.65, "cuda": 0.9, "cpu": 0.7}
HUBS = ("huggingface", "modelscope")


class ScoutError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch(url, timeout, accept="application/json", body=None):
    headers = {"Accept": accept, "User-Agent": "tunetune-scout/1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, headers=headers, method="PUT" if body is not None else "GET",
                      data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
            headers = response.headers
    except HTTPError as exc:
        retry = exc.headers.get("retry-after") if exc.headers else None
        if exc.code == 429 or exc.code == 403 and exc.headers and exc.headers.get("x-ratelimit-remaining") == "0":
            raise ScoutError("rate_limited", f"{url} is rate limited; wait before retrying", retry) from None
        if exc.code == 404:
            raise ScoutError("not_found", f"{url} was not found") from None
        if exc.code == 401 or exc.code == 403:
            raise ScoutError("restricted", f"{url} requires access this tool does not have") from None
        raise ScoutError("http_error", f"{url} returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise ScoutError("unreachable", f"{url} could not be reached: {getattr(exc, 'reason', exc)}") from None
    if len(data) > MAX_BYTES:
        raise ScoutError("too_large", f"{url} returned more than {MAX_BYTES} bytes")
    limits = {k: headers.get(k) for k in ("ratelimit", "x-ratelimit-remaining", "x-ratelimit-reset") if headers.get(k)}
    if accept != "application/json":
        return data.decode("utf-8", "replace"), limits
    try:
        return json.loads(data), limits
    except json.JSONDecodeError:
        raise ScoutError("invalid_response", f"{url} did not return JSON") from None


def license_info(tags, explicit=None):
    found = explicit or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
    if not found:
        return {"id": None, "class": "unknown"}
    value = found.lower()
    kind = "permissive" if value in PERMISSIVE else "copyleft" if value in COPYLEFT else "restricted_or_custom"
    return {"id": found, "class": kind}


def hf_item(raw, kind):
    tags = raw.get("tags") or []
    unknown = []
    item = {"hub": "huggingface", "id": raw.get("id"), "url": f"{HF}/{'datasets/' if kind == 'dataset' else ''}{raw.get('id')}",
            "downloads": raw.get("downloads"), "likes": raw.get("likes"),
            "last_modified": raw.get("lastModified"), "gated": raw.get("gated", False),
            "license": license_info(tags, (raw.get("cardData") or {}).get("license") if isinstance((raw.get("cardData") or {}).get("license"), str) else None),
            "languages": sorted(t.split(":", 1)[1] for t in tags if t.startswith("language:"))
            or sorted(t for t in tags if len(t) == 2 and t.isalpha())}
    if kind == "model":
        item["task"] = raw.get("pipeline_tag")
        item["library"] = raw.get("library_name")
        total = (raw.get("safetensors") or {}).get("total") or (raw.get("gguf") or {}).get("total")
        item["params"] = {"value": total, "source": "safetensors" if (raw.get("safetensors") or {}).get("total") else "gguf"} if total else None
    else:
        item["tasks"] = sorted(t.split(":", 1)[1] for t in tags if t.startswith("task_categories:"))
        item["size"] = next((t.split(":", 1)[1] for t in tags if t.startswith("size_categories:")), None)
    for key, value in item.items():
        if value is None or value == []:
            unknown.append(key)
    item["unknown"] = unknown
    return item


def hf_search(args, kind):
    params = [("search", args.query)] if args.query else []
    params += [("filter", value) for value in (args.filter or [])]
    if args.lang:
        params.append(("filter", args.lang if kind == "model" else f"language:{args.lang}"))
    if kind == "model":
        if args.task:
            params.append(("pipeline_tag", args.task))
        if args.library:
            params.append(("library", args.library))
    elif args.task:
        params.append(("filter", f"task_categories:{args.task}"))
    sort = {"downloads": "downloads", "likes": "likes", "trending": "trendingScore", "recent": "lastModified"}[args.sort]
    params += [("sort", sort), ("direction", "-1"), ("limit", str(min(args.limit * 3, 100)))]
    expand = ["downloads", "likes", "tags", "lastModified", "gated"]
    expand += ["safetensors", "pipeline_tag", "library_name"] if kind == "model" else []
    params += [("expand[]", value) for value in expand]
    raw, limits = fetch(f"{HF}/api/{kind}s?{urlencode(params)}", args.timeout)
    items = [hf_item(entry, kind) for entry in raw]
    if args.min_downloads:
        items = [i for i in items if (i["downloads"] or 0) >= args.min_downloads]
    if kind == "model" and args.max_params:
        items = [i for i in items if i["params"] and i["params"]["value"] <= args.max_params]
    if args.license:
        items = [i for i in items if i["license"]["class"] == args.license]
    warnings = ["Search relevance is weak; prefer short queries with task and language filters",
                "Downloads and likes show popularity, not suitability for this study"]
    return items[:args.limit], limits, warnings, {"matched_before_limit": len(items)}


def ms_fetch(path, timeout, body=None):
    """ModelScope wraps results as {Code, Data, Message}; a non-200 Code is an error even over HTTP 200."""
    raw, limits = fetch(f"{MODELSCOPE}/api/v1/{path}", timeout, body=body)
    if not isinstance(raw, dict) or raw.get("Code") != 200 or not isinstance(raw.get("Data"), dict):
        message = str(raw.get("Message") or "unexpected response")[:200] if isinstance(raw, dict) else "unexpected response"
        code = "not_found" if "404" in message or "不存在" in message else "http_error"
        raise ScoutError(code, f"ModelScope {path.split('?')[0]}: {message}")
    return raw["Data"], limits


def ms_time(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z") if isinstance(value, (int, float)) and value > 0 else None


def ms_item(raw):
    ident = f"{raw.get('Path')}/{raw.get('Name')}" if raw.get("Path") and raw.get("Name") else None
    tasks = [t.get("Name") for t in raw.get("Tasks") or [] if isinstance(t, dict) and t.get("Name")]
    total = ((raw.get("ModelInfos") or {}).get("safetensor") or {}).get("model_size")
    item = {"hub": "modelscope", "id": ident, "url": f"{MODELSCOPE}/models/{ident}", "downloads": raw.get("Downloads"),
            "likes": raw.get("Stars"), "last_modified": ms_time(raw.get("LastUpdatedTime")),
            "gated": raw.get("IsAccessible") != 1, "license": license_info([], raw.get("License") or None),
            "languages": sorted(raw.get("Language") or []), "task": tasks[0] if tasks else None,
            "library": next((x for x in raw.get("Libraries") or [] if x not in ("pytorch", "safetensors")), None),
            "params": {"value": total, "source": "safetensors"} if isinstance(total, int) and total > 0 else None}
    item["unknown"] = [k for k, v in item.items() if v is None or v == []]
    return item


def ms_search(args):
    criteria = [{"category": category, "predicate": "contains", "values": [value]}
                for category, value in (("tasks", args.task), ("languages", args.lang)) if value]
    sort = {"downloads": "DownloadsCount", "likes": "StarsCount", "trending": "Default", "recent": "GmtModified"}[args.sort]
    body = {"PageSize": min(args.limit * 3, 100), "PageNumber": 1, "SortBy": sort, "Target": "",
            "Criterion": criteria, "SingleCriterion": [], "Name": args.query or ""}
    data, limits = ms_fetch("dolphin/models", args.timeout, body)
    items = [ms_item(entry) for entry in (data.get("Model") or {}).get("Models") or []]
    if args.library:
        items = [i for i in items if i["library"] == args.library]
    if args.min_downloads:
        items = [i for i in items if (i["downloads"] or 0) >= args.min_downloads]
    if args.max_params:
        items = [i for i in items if i["params"] and i["params"]["value"] <= args.max_params]
    if args.license:
        items = [i for i in items if i["license"]["class"] == args.license]
    warnings = ["ModelScope search uses its website endpoint and may change; inspect candidates before relying on them",
                "Downloads and likes show popularity, not suitability for this study"]
    return items[:args.limit], limits, warnings, {"matched_before_limit": len(items),
                                                    "total_count": (data.get("Model") or {}).get("TotalCount")}


def ms_files(name, revision, timeout):
    data, limits = ms_fetch(f"models/{quote(name, safe='/')}/repo/files?{urlencode({'Revision': revision or 'master', 'Recursive': 'true'})}", timeout)
    files = [f for f in data.get("Files") or [] if isinstance(f, dict) and f.get("Type") == "blob"]
    short = (data.get("LatestCommitter") or {}).get("ShortId") or ""
    # The API reports a short commit; resolve it against the full file revisions it lists.
    full = next((f["Revision"] for f in files if short and str(f.get("Revision", "")).startswith(short)), None)
    if revision and len(revision) == 40 and short and revision.startswith(short):
        full = revision
    return files, full, limits


def ms_inspect(args):
    if args.kind != "model":
        raise ScoutError("unsupported", "ModelScope lookup covers models only; use Hugging Face for datasets")
    query = f"?{urlencode({'Revision': args.revision})}" if args.revision else ""
    raw, limits = ms_fetch(f"models/{quote(args.name, safe='/')}{query}", args.timeout)
    item = ms_item(raw)
    files, revision, more = ms_files(args.name, args.revision, args.timeout)
    limits.update(more)
    item["revision"] = revision
    item["config"] = {k: v for k, v in (("architectures", raw.get("Architectures")), ("model_type", (raw.get("ModelType") or [None])[0])) if v} or None
    listed = [{"path": f.get("Path"), "size": f.get("Size"), "sha256": f.get("Sha256") or None} for f in files]
    item["files"] = listed[:200]
    item["total_file_bytes"] = sum(f["size"] or 0 for f in listed)
    item["unknown"] = [k for k, v in item.items() if k != "unknown" and (v is None or v == [])]
    return [item], limits, ["Files list up to 200 entries"] if len(listed) > 200 else [], {}


def inspect(args):
    if args.hub == "modelscope":
        return ms_inspect(args)
    kind = args.kind
    path = f"{HF}/api/{kind}s/{quote(args.name, safe='/')}"
    if args.revision:
        path += f"/revision/{quote(args.revision)}"
    expand = ["downloads", "likes", "tags", "lastModified", "gated", "cardData", "sha"]
    expand += ["safetensors", "gguf", "pipeline_tag", "library_name", "config"] if kind == "model" else []
    raw, limits = fetch(path + "?" + urlencode([("expand[]", e) for e in expand]), args.timeout)
    item = hf_item(raw, kind)
    item["revision"] = raw.get("sha")
    gguf = raw.get("gguf") or {}
    if gguf:
        item["gguf"] = {k: gguf.get(k) for k in ("architecture", "context_length", "total") if k in gguf}
    config = raw.get("config") or {}
    item["config"] = {k: config.get(k) for k in ("architectures", "model_type") if k in config} or None
    tree, more = fetch(f"{HF}/api/{kind}s/{quote(args.name, safe='/')}/tree/{quote(args.revision or 'main')}", args.timeout)
    limits.update(more)
    files = [{"path": f["path"], "size": f.get("size")} for f in tree if f.get("type") == "file"]
    item["files"] = files[:200]
    item["total_file_bytes"] = sum(f["size"] or 0 for f in files)
    item["unknown"] = [k for k, v in item.items() if k != "unknown" and (v is None or v == [])]
    return [item], limits, ["Files list only the root of the repository"] if any(f.get("type") == "directory" for f in tree) else [], {}


def model_shape(name, timeout, hub="huggingface"):
    """Return parameters and attention shape from public metadata, marking estimates."""
    if hub == "modelscope":
        raw, _ = ms_fetch(f"models/{quote(name, safe='/')}", timeout)
        total = ((raw.get("ModelInfos") or {}).get("safetensor") or {}).get("model_size")
        try:
            config, _ = fetch(f"{MODELSCOPE}/api/v1/models/{quote(name, safe='/')}/repo?{urlencode({'Revision': 'master', 'FilePath': 'config.json'})}", timeout)
        except ScoutError:
            config = {}
        return (total if isinstance(total, int) and total > 0 else None), (config if isinstance(config, dict) else {})
    raw, _ = fetch(f"{HF}/api/models/{quote(name, safe='/')}?" + urlencode([("expand[]", e) for e in ("safetensors", "gguf")]), timeout)
    total = (raw.get("safetensors") or {}).get("total") or (raw.get("gguf") or {}).get("total")
    try:
        config, _ = fetch(f"{HF}/{quote(name, safe='/')}/resolve/main/config.json", timeout)
    except ScoutError:
        config = {}
    return total, config


def fit(args):
    assumptions, unknown = [], []
    params, config = args.params, {}
    source = "argument" if params else None
    if args.name:
        found, config = model_shape(args.name, args.timeout, args.hub)
        if not params and found:
            params, source = found, "metadata"
    usable = args.memory_gb * USABLE_SHARE[args.platform]
    assumptions.append(f"usable memory is about {int(USABLE_SHARE[args.platform] * 100)}% of {args.memory_gb} GB on {args.platform}")
    result = {"name": args.name, "memory_gb": args.memory_gb, "usable_gb": round(usable, 2), "mode": args.mode,
              "precision": args.precision, "params": params, "params_source": source}
    if not params:
        result.update(verdict="unknown", weights_gb=None, kv_cache_gb=None, training_extra_gb=None)
        unknown.append("params")
    else:
        weights = params * BYTES_PER_PARAM[args.precision] / 1e9
        assumptions.append(f"{BYTES_PER_PARAM[args.precision]} bytes per parameter for {args.precision}")
        layers = config.get("num_hidden_layers")
        heads = config.get("num_attention_heads")
        kv_heads = config.get("num_key_value_heads") or heads
        hidden = config.get("hidden_size")
        head_dim = config.get("head_dim") or (hidden // heads if hidden and heads else None)
        if layers and kv_heads and head_dim:
            kv = 2 * layers * kv_heads * head_dim * args.context * args.batch * 2 / 1e9
            assumptions.append(f"fp16 key/value cache for {args.context} tokens and batch {args.batch}")
        else:
            kv = None
            unknown.append("kv_cache_gb")
        if args.mode == "full-finetune":
            extra = params * 16 / 1e9 - weights
            assumptions.append("mixed-precision AdamW needs about 16 bytes per parameter before activations")
        elif args.mode == "lora":
            extra = weights * 0.2
            assumptions.append("adapters and optimizer state add about 20% of base weights before activations")
        else:
            extra = 0.0
        if args.mode != "inference":
            unknown.append("activations")
        total = weights + (kv or 0) + extra
        # Training leaves room for unmeasured activations; inference keeps a smaller margin.
        headroom = 0.5 if args.mode != "inference" else 0.8
        verdict = "fits" if total <= usable * headroom else "tight" if total <= usable else "no"
        result.update(weights_gb=round(weights, 2), kv_cache_gb=round(kv, 2) if kv is not None else None,
                      training_extra_gb=round(extra, 2) if args.mode != "inference" else None,
                      estimated_total_gb=round(total, 2), verdict=verdict)
    result.update(confidence="low" if unknown else "medium", assumptions=assumptions, unknown=unknown)
    return [result], {}, ["Estimates only; measure real memory with a small end-to-end check"], {}


def papers(args):
    if args.source == "hf":
        raw, limits = fetch(f"{HF}/api/papers/search?{urlencode({'q': args.query})}", args.timeout)
        items = []
        for entry in raw[:args.limit]:
            paper = entry.get("paper", entry)
            items.append({"id": paper.get("id"), "title": paper.get("title") or entry.get("title"),
                          "url": f"{HF}/papers/{paper.get('id')}", "published": paper.get("publishedAt"),
                          "summary": (paper.get("summary") or "")[:600], "upvotes": paper.get("upvotes")})
        return items, limits, [], {}
    query = urlencode({"search_query": f"all:{args.query}", "max_results": args.limit, "sortBy": "relevance"})
    text, limits = fetch(f"{ARXIV}/api/query?{query}", args.timeout, accept="application/atom+xml")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in ET.fromstring(text).findall("a:entry", ns):
        get = lambda tag: (entry.findtext(f"a:{tag}", default="", namespaces=ns) or "").strip()
        items.append({"id": get("id").rsplit("/", 1)[-1], "title": " ".join(get("title").split()), "url": get("id"),
                      "published": get("published"), "summary": " ".join(get("summary").split())[:600]})
    return items, limits, ["arXiv asks for about one request every three seconds"], {}


def repos(args):
    query = args.query + (f" language:{args.language}" if args.language else "")
    raw, limits = fetch(f"{GITHUB}/search/repositories?{urlencode({'q': query, 'sort': 'stars', 'per_page': args.limit})}", args.timeout)
    items = [{"id": r.get("full_name"), "url": r.get("html_url"), "description": (r.get("description") or "")[:300],
              "stars": r.get("stargazers_count"), "pushed_at": r.get("pushed_at"), "archived": r.get("archived"),
              "license": license_info([], (r.get("license") or {}).get("spdx_id"))} for r in raw.get("items", [])]
    return items, limits, ["Unauthenticated search allows about 10 requests per minute; stars show popularity, not fit"], {"total_count": raw.get("total_count")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("models", "datasets"):
        command = commands.add_parser(name)
        command.add_argument("--query")
        command.add_argument("--task")
        command.add_argument("--lang")
        command.add_argument("--filter", action="append")
        command.add_argument("--sort", choices=("downloads", "likes", "trending", "recent"), default="downloads")
        command.add_argument("--min-downloads", type=int)
        command.add_argument("--license", choices=("permissive", "copyleft", "restricted_or_custom", "unknown"))
        if name == "models":
            command.add_argument("--library")
            command.add_argument("--max-params", type=float)
            command.add_argument("--hub", choices=HUBS, default="huggingface")
    command = commands.add_parser("inspect")
    command.add_argument("name")
    command.add_argument("--kind", choices=("model", "dataset"), default="model")
    command.add_argument("--revision")
    command.add_argument("--hub", choices=HUBS, default="huggingface")
    command = commands.add_parser("fit")
    command.add_argument("name", nargs="?")
    command.add_argument("--hub", choices=HUBS, default="huggingface")
    command.add_argument("--params", type=float, help="parameter count when metadata is unavailable")
    command.add_argument("--memory-gb", type=float, required=True)
    command.add_argument("--platform", choices=tuple(USABLE_SHARE), default="cpu")
    command.add_argument("--mode", choices=("inference", "lora", "full-finetune"), default="inference")
    command.add_argument("--precision", choices=tuple(BYTES_PER_PARAM), default="fp16")
    command.add_argument("--context", type=int, default=4096)
    command.add_argument("--batch", type=int, default=1)
    command = commands.add_parser("papers")
    command.add_argument("--query", required=True)
    command.add_argument("--source", choices=("arxiv", "hf"), default="arxiv")
    command = commands.add_parser("repos")
    command.add_argument("--query", required=True)
    command.add_argument("--language")
    for command in commands.choices.values():
        command.add_argument("--limit", type=int, default=10)
        command.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 50 or args.timeout <= 0:
        parser.error("--limit must be 1-50 and --timeout positive")
    if args.command == "fit" and not args.name and not args.params:
        parser.error("fit needs a model name or --params")
    handlers = {"models": lambda a: ms_search(a) if a.hub == "modelscope" else hf_search(a, "model"), "datasets": lambda a: hf_search(a, "dataset"),
                "inspect": inspect, "fit": fit, "papers": papers, "repos": repos}
    query = {k: v for k, v in vars(args).items() if k not in ("command", "timeout") and v is not None}
    try:
        results, limits, warnings, coverage = handlers[args.command](args)
    except ScoutError as exc:
        print(json.dumps({"tool": "scout", "command": args.command, "query": query,
                          "error": {"code": exc.code, "message": str(exc), "retry_after_s": exc.retry_after}},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"tool": "scout", "version": 1, "command": args.command, "retrieved_at": now(), "query": query,
                      "results": results, "coverage": {"returned": len(results), **coverage}, "limits": limits,
                      "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
