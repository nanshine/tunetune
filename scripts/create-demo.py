#!/usr/bin/env python3
"""Create a local synthetic classical-classifier demo in a fresh format-3 project.

No dependencies, network access, installation, or model downloads. Existing research
is refused, including partial prior demo runs. Invoke only after installing a kit:
    python3 scripts/create-demo.py --project /absolute/installed-project
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

NOTICE = "合成数据原型 / 微型经典分类器；不是 LLM 微调质量证据。"
SOURCE = "本地编写的合成英文消息"
LABELS = ("todo", "expense", "appointment", "other")
DELIVERIES = ["exp-001", "exp-002", "exp-008"]
HELPERS = ".agents/skills/research-workspace/scripts"
RUBRIC = (
    "按消息的主要意图单标签分类：todo=需要执行的任务（含待支付账单）；"
    "expense=已发生消费、收据或费用通知；appointment=已约定的会面或改期/取消通知；"
    "other=闲聊、新闻、无行动的信息。明确任务优先于仅被提及的账单/会议词，"
    "安排好的会面通知不是待办。歧义按此约定标注。"
    "accuracy=正确数/样例数；macro_f1=四类 F1 的算术平均，"
    "F1=2TP/(2TP+FP+FN)，分母为零取0。逐例 scores.accuracy 是0/1；"
    "macro_f1只在整个样例集上计算。"
)

# The pools are authored separately, never sampled from training or augmentation.
TRAIN = {
    "todo": [
        "Please send the revised report", "Remember to buy bread", "Finish the draft tonight",
        "Call the supplier about the order", "Please review the budget spreadsheet",
        "Submit the application before Friday", "Pick up the parcel at the shop",
        "Remember to pay the electricity bill", "Please book a room for the workshop",
        "Prepare slides for the team", "Update the address in the form",
        "Please email the notes to the group", "Check the invoice before paying",
        "Clean the kitchen after lunch", "Bring your notebook tomorrow", "Please fix the broken link",
    ],
    "expense": [
        "Receipt for lunch total 12 dollars", "Your payment of 24 dollars was received",
        "Taxi fare charged to your card", "The grocery purchase cost 35 dollars",
        "Subscription renewed for 8 dollars", "Invoice paid for office supplies",
        "Refund of 15 dollars processed", "Coffee receipt total 4 dollars",
        "Your train ticket purchase is complete", "Monthly service fee charged today",
        "Hotel bill paid in full", "Dinner cost 19 dollars yesterday",
    ],
    "appointment": [
        "Dentist appointment on Monday at ten", "Team meeting scheduled for tomorrow",
        "Your haircut is booked for Friday", "Lunch with the team at noon on Tuesday",
        "Doctor visit confirmed for next week", "The interview starts at nine on Thursday",
        "Our call is scheduled for three", "Workshop moved to Wednesday afternoon",
        "Your consultation is cancelled today", "The class will meet on Saturday morning",
        "Reservation confirmed for dinner at seven", "Therapy session postponed until Monday",
    ],
    "other": [
        "Have a lovely weekend", "The sunset looks beautiful", "Here is a funny story",
        "Thanks for your kind words", "The weather is warm today", "A new album is out",
        "I enjoyed the film last night", "The garden is full of flowers",
        "That was an interesting article", "Our team won the game", "The cat is sleeping",
        "Good morning everyone",
    ],
}
EASY = {
    "todo": ["Please send the invoice copy", "Remember to buy tea", "Finish the report today", "Review the application draft"],
    "expense": ["Receipt for groceries total 18 dollars", "Taxi payment of 9 dollars received", "Your card was charged a service fee", "Coffee purchase cost 3 dollars"],
    "appointment": ["Dentist appointment confirmed for Tuesday", "Team meeting scheduled at noon", "Your interview moved to Friday", "Doctor visit booked for Monday"],
    "other": ["Have a beautiful morning", "The garden looks lovely", "Thanks for the funny story", "I enjoyed the new album"],
}
EDGE = {
    "todo": [
        "Please pay the hotel invoice tomorrow", "Remember to cancel the dentist booking",
        "Could you send the receipt to the team", "Fix the meeting link before lunch",
        "Please review my subscription charges", "Email the refund request before Friday",
    ],
    "expense": [
        "Your appointment deposit of 30 dollars was charged", "Paid for the workshop yesterday",
        "The lunch refund is complete", "Grocery bill settled this morning",
        "SUBSCRIPTION RENEWED: 11 dollars", "Taxi fare chargd to your card",
    ],
    "appointment": [
        "Our meeting is no longer on Tuesday; it moved to Friday", "Dentist apointment at ten tomorrow",
        "Your consultation is now a video call at noon", "Lunch reservation cancelled for Saturday",
        "Reminder: the interview starts at 14:00", "The class has been postponed to next week",
    ],
    "other": [
        "The film about a bank payment was funny", "Thanks, the report was an interesting read",
        "I remember our lovely dinner", "No action needed, just a sunny day",
        "The article tells the history of the taxi", "The meeting scene in that movie was beautiful",
    ],
}
COMPARISON = [
    "Please pay the water bill before Monday", "Your card was charged 21 dollars for dinner",
    "Dentist appointment moved to Thursday at noon", "Have a relaxing evening",
    "Please send the meeting notes", "Thanks for the story about the invoice",
    "Haircut apointment confirmed for Saturday", "Subscription refund of 6 dollars processed",
]

# Only necessary execution sources are frozen. Inference never reads evaluation
# labels, training files, or a sample lookup table.
INFER_SOURCE = r'''"""Synthetic-data prototype, tiny classical classifier, NOT LLM quality evidence."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

LABELS = ("todo", "expense", "appointment", "other")
NOTICE = "Synthetic-data prototype; tiny classical classifier; NOT LLM fine-tuning evidence."


def features(text, parameters):
    words = re.findall(r"[a-z]+|[0-9]+", text.lower())
    mode = parameters["features"]
    result = Counter()
    if mode in ("word", "mixed"):
        result.update("w:" + word for word in words)
    if mode in ("char", "mixed"):
        normalized = " " + " ".join(words) + " "
        for n in range(parameters.get("ngram_min", 3), parameters.get("ngram_max", 3) + 1):
            result.update("c:" + normalized[i:i+n] for i in range(len(normalized) - n + 1))
    if parameters.get("binary"):
        result = Counter({key: 1 for key in result})
    return result


def predict(model, text):
    if not isinstance(text, str):
        raise ValueError("input must be text")
    if model["kind"] == "keyword":
        words = Counter(re.findall(r"[a-z]+", text.lower()))
        scores = {label: model["bias"][label] + sum(words[word] * weight
                  for word, weight in model["weights"][label].items()) for label in LABELS}
    else:
        counts = features(text, model["parameters"])
        scores = {label: model["log_prior"][label] + sum(
            count * model["log_likelihood"][label].get(feature, 0.0)
            for feature, count in counts.items()) for label in LABELS}
    # Stable, deterministic tie-breaking follows LABELS; unknown NB features ignored.
    label = max(LABELS, key=lambda item: scores[item])
    maximum = max(scores.values())
    masses = {key: math.exp(value - maximum) for key, value in scores.items()}
    total = sum(masses.values())
    return label, {key: value / total for key, value in masses.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--inputs", help="JSONL objects with sample_id and input")
    group.add_argument("--jsonl", nargs=2, metavar=("INPUT", "OUTPUT"), help="invoke.json entry point")
    args = parser.parse_args()
    model = json.loads(Path(args.model).read_text(encoding="utf-8"))
    if args.text is not None:
        print(predict(model, args.text)[0])
    elif args.jsonl:
        rows = [json.loads(line) for line in Path(args.jsonl[0]).read_text(encoding="utf-8").splitlines() if line.strip()]
        with Path(args.jsonl[1]).open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps({"sample_id": row["sample_id"], "output": predict(model, row["input"])[0]},
                                        ensure_ascii=False) + "\n")
    else:
        rows = [json.loads(line) for line in Path(args.inputs).read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            label, probabilities = predict(model, row["input"])
            print(json.dumps({"sample_id": row["sample_id"], "input": row["input"],
                              "output": label, "probabilities": probabilities}))


if __name__ == "__main__":
    main()
'''

TRAIN_SOURCE = r'''"""Train a synthetic-data tiny classical classifier, NOT an LLM."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
from infer import LABELS, NOTICE, features


def training_rows(rows, augment):
    result = list(rows)
    if augment:
        # Entirely train-derived transformations: no evaluation vocabulary/labels read.
        synonyms = {"please": "kindly", "remember": "don't forget", "buy": "purchase",
                    "charged": "billed", "appointment": "booking", "meeting": "session",
                    "lovely": "nice", "send": "forward"}
        for row in rows:
            words = row["input"].lower().split()
            transformed = " ".join(synonyms.get(word, word) for word in words)
            result.append({"input": transformed, "reference": row["reference"]})
            # Simulate one dropped character, deterministically, in a long word.
            for index, word in enumerate(words):
                if len(word) >= 6:
                    words[index] = word[:3] + word[4:]
                    break
            result.append({"input": " ".join(words), "reference": row["reference"]})
    return result


def train(rows, parameters):
    used = training_rows(rows, parameters.get("augmentation", False))
    base = {"schema_version": 1, "notice": NOTICE, "labels": list(LABELS),
            "kind": parameters["kind"], "parameters": parameters,
            "training_rows": len(rows), "effective_training_rows": len(used)}
    if parameters["kind"] == "keyword":
        # A real fixed-rule baseline, not claimed to be trained or fine-tuned.
        terms = {"todo": "please remember finish submit review send buy fix",
                 "expense": "receipt payment paid charged cost fee invoice refund",
                 "appointment": "appointment meeting scheduled booked interview reservation",
                 "other": "lovely thanks beautiful funny enjoyed"}
        base.update(weights={label: {word: 1.0 for word in terms[label].split()} for label in LABELS},
                    bias={label: 0.05 if label == "other" else 0.0 for label in LABELS},
                    fitted=False)
        return base
    counts = {label: Counter() for label in LABELS}
    documents = Counter()
    for row in used:
        label = row["reference"]
        if label not in LABELS:
            raise ValueError("Unknown training label")
        documents[label] += 1
        counts[label].update(features(row["input"], parameters))
    vocabulary = sorted(set().union(*(set(counts[label]) for label in LABELS)))
    alpha = parameters["alpha"]
    if alpha <= 0 or not vocabulary:
        raise ValueError("Need positive smoothing and nonempty vocabulary")
    if parameters["prior"] == "empirical":
        priors = {label: documents[label] / len(used) for label in LABELS}
    elif parameters["prior"] == "task_weighted":
        priors = dict(zip(LABELS, (0.4, 0.2, 0.2, 0.2)))
    else:
        priors = {label: 0.25 for label in LABELS}
    base.update(fitted=True, vocabulary_size=len(vocabulary), class_counts=dict(documents),
                log_prior={label: math.log(priors[label]) for label in LABELS},
                log_likelihood={label: {feature: math.log((counts[label][feature] + alpha) /
                    (sum(counts[label].values()) + alpha * len(vocabulary)))
                    for feature in vocabulary} for label in LABELS})
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--output", required=True, help="New model.json; refuses overwrite")
    args = parser.parse_args()
    data = Path(args.data).read_bytes()
    parameters = json.loads(Path(args.parameters).read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    model = train(rows, parameters)
    model["training_sha256"] = hashlib.sha256(data).hexdigest()
    with Path(args.output).open("x", encoding="utf-8") as stream:
        json.dump(model, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"kind": model["kind"], "fitted": model["fitted"],
                      "training_rows": model["training_rows"], "effective_training_rows": model["effective_training_rows"],
                      "vocabulary_size": model.get("vocabulary_size", 0), "output": args.output}))
    print("Completed local parameter generation.", file=sys.stderr)


if __name__ == "__main__":
    main()
'''

EVALUATE_SOURCE = r'''"""Frozen development evaluation for synthetic tiny models, NOT LLM evidence.

--model MODEL --samples JSONL emits {metrics, outputs} JSON to stdout.
--self-test checks perfect, wrong, and partial predictions including macro F1.
"""
import argparse
import json
from pathlib import Path
from infer import LABELS, predict


def metrics(references, predictions):
    if not references or len(references) != len(predictions):
        raise ValueError("Evaluation requires equal nonempty reference/prediction lists")
    if any(label not in LABELS for label in references + predictions):
        raise ValueError("Unknown label")
    f1 = []
    for label in LABELS:
        tp = sum(a == label and b == label for a, b in zip(references, predictions))
        fp = sum(a != label and b == label for a, b in zip(references, predictions))
        fn = sum(a == label and b != label for a, b in zip(references, predictions))
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return {"accuracy": sum(a == b for a, b in zip(references, predictions)) / len(references),
            "macro_f1": sum(f1) / len(LABELS)}


def self_test():
    labels = list(LABELS)
    assert metrics(labels, labels) == {"accuracy": 1.0, "macro_f1": 1.0}
    assert metrics(labels, labels[1:] + labels[:1]) == {"accuracy": 0.0, "macro_f1": 0.0}
    partial = metrics(labels, ["todo", "todo", "appointment", "other"])
    assert partial["accuracy"] == 0.75
    assert abs(partial["macro_f1"] - 2 / 3) < 1e-12
    assert metrics(["todo"], ["todo"])["macro_f1"] == 0.25
    try:
        metrics([], [])
    except ValueError:
        pass
    else:
        raise AssertionError("Empty evaluation accepted")
    return {"passed": True, "checks": 5}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--samples")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()))
        return
    if not args.model or not args.samples:
        parser.error("--model and --samples are required unless --self-test")
    model = json.loads(Path(args.model).read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in Path(args.samples).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({row["sample_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate sample id")
    outputs = []
    for row in rows:
        label, _ = predict(model, row["input"])
        outputs.append({"sample_id": row["sample_id"], "input": row["input"], "output": label,
                        "reference": row["reference"], "scores": {"accuracy": int(label == row["reference"])}})
    print(json.dumps({"metrics": metrics([row["reference"] for row in rows], [row["output"] for row in outputs]),
                      "outputs": outputs}))


if __name__ == "__main__":
    main()
'''

# Parent IDs describe code ancestry ONLY. Every fit starts from scratch.
VARIANTS = [
    ("关键词规则基线", None, "固定词权重给出可解释下限；基线不经过训练。", {"kind": "keyword"}),
    ("词袋朴素贝叶斯", 1, "词频似然可取代手写关键词，检验简单统计学习的变化。", {}),
    ("低平滑词袋", 2, "减小加性平滑可能保留稀有意图词，也可能更易过拟合。", {"alpha": 0.1}),
    ("字符三元组", 2, "字符局部模式可能缓和词形变化，但也可能混淆近似词。", {"features": "char"}),
    ("多尺度字符片段", 4, "组合二至四元字符片段观察覆盖率和特征冗余的取舍。", {"features": "char", "ngram_min": 2, "ngram_max": 4}),
    ("词与字符混合", 5, "在v2边界集上检查混合特征能否保留意图词和拼写容错。", {"features": "mixed"}),
    ("词袋训练增强", 2, "只用训练消息生成同义替换和删字变体，观察词袋鲁棒性。", {"augmentation": True}),
    ("混合二值特征与增强", 6, "增强加二值计数减少重复字符影响，观察组合效果而非单因素因果。", {"features": "mixed", "augmentation": True, "binary": True, "alpha": 0.5}),
    ("经验类别先验", 2, "训练集待办更多；用经验先验检验类别分布假设。", {"prior": "empirical"}),
    ("偏重待办的先验", 9, "设定待办先验0.4，检查任务召回与误报的取舍。", {"prior": "task_weighted"}),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def rows(pool, prefix):
    return [{"sample_id": f"{prefix}-{label}-{index:02d}", "input": text,
             "reference": label, "source": SOURCE}
            for label, texts in pool.items() for index, text in enumerate(texts, 1)]


def jsonl(items):
    return "".join(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n" for item in items).encode()


def load_records(project):
    """Reject symlinks before importing the explicitly installed, trusted helper."""
    if ".." in os.fspath(project).split("/"):
        raise ValueError("Parent traversal is not allowed")
    project = Path(os.path.abspath(project))
    helper = project / HELPERS / "records.py"
    for path in reversed((helper, *helper.parents)):
        if path.is_symlink():
            raise ValueError(f"Symlinks are not supported: {path}")
    if not helper.is_file():
        raise ValueError("Install the core kit with the agents host before generating a demo")
    spec = importlib.util.spec_from_file_location("tunetune_demo_records", helper)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return project, module


class Demo:
    def __init__(self, project, records, tree, staging):
        self.project, self.records, self.tree, self.staging = project, records, tree, staging
        self.initial = {}
        self.models = {}
        self.evaluations = {}
        self.python = sys.executable

    def preflight(self):
        for path in ("project.json", "proposal.json", "resources.json"):
            data = self.tree.read(path)
            self.records.shape(path, data)
            self.initial[path] = self.records.digest(data)
        manifest = self.read_json(".workspace/manifest.json")
        if not manifest.get("schema_min", 4) == 3 == manifest.get("schema_max", 0):
            raise ValueError("Installed kit does not support schema 3")
        for path in ("AGENTS.md", ".workspace/app/workspace.py", ".workspace/app/monitor.py",
                     ".workspace/app/assets/index.html", HELPERS + "/run.py"):
            if not self.tree.read(path):
                raise ValueError(f"Missing installed core file: {path}")
        for directory in ("data", "src", "evaluation", "experiments", "comparison"):
            if self.tree.exists(directory):
                with self.tree.directory(self.records.parts(directory)) as folder:
                    if os.listdir(folder):
                        raise ValueError(f"Refusing existing research in {directory}; use a fresh installed project")
        project, proposal = self.read_json("project.json"), self.read_json("proposal.json")
        if (project["current_evaluation"] is not None or project["deliveries"]
                or proposal["summary"] or proposal["sections"] or proposal["examples"] or "feasibility" in proposal
                or proposal.get("approaches") or self.read_json("resources.json")["items"]):
            raise ValueError("Refusing an existing proposal, evaluation, delivery, or resource inventory")
        report = self.records.validate(self.tree)
        if not report["valid"]:
            raise ValueError(f"Installed project is invalid: {report['errors']}")
        # Also reject unsafe installed files before any publication. No persistent
        # generation marker: the first proposal write already reserves this demo.
        self.initial_files = set(self.tree.files(""))

    def read_json(self, path):
        return self.records.strict(self.tree.read(path))

    def sha(self, path):
        return self.records.digest(self.tree.read(path))

    def raw(self, path, value):
        data = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else self.records.encoded(value)
        self.tree.publish(path, data)

    def record(self, path, value, expected=None):
        data = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else self.records.encoded(value)
        source = self.staging / "record-input"
        source.write_bytes(data)
        return self.records.write(self.tree, path, source, create=expected is None, expected=expected)

    def execution(self, argv):
        return {"argv": argv, "cwd": ".", "timeout_seconds": 60,
                "environment": {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}}

    def run(self, base):
        """Let the installed runner own reservation, process cleanup and status.

        Never hold tree.locked() here: the CLI acquires that lock itself. The
        runner enforces the config timeout; stdout is status, run.log is payload.
        """
        argv = [self.python, "-B", str(self.project / HELPERS / "run.py"),
                "--project", str(self.project), "--path", base]
        result = subprocess.run(argv, cwd=self.project, env=self.execution(argv)["environment"],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Command failed at {base}: {result.stderr.strip() or result.stdout.strip()}")
        status = self.records.strict(result.stdout)
        if status != self.read_json(base + "/status.json") or status.get("state") != "completed":
            raise ValueError(f"Runner did not leave completed process evidence at {base}")
        return status

    def finish(self, base, state="succeeded", **details):
        path = base + "/status.json"
        previous = self.tree.read(path)
        status = self.records.strict(previous)
        if state == "succeeded" and status["state"] != "completed":
            raise ValueError("Only verified completed attempts can succeed")
        self.record(path, {**status, **details, "state": state, "updated_at": now()}, self.records.digest(previous))

    def fail(self, base, error):
        if self.read_json(base + "/status.json")["state"] not in self.records.FINAL:
            self.finish(base, "failed", error=str(error))

    def helper(self, argv):
        """Bounded, non-study calibration/comparison helper; one combined output."""
        result = subprocess.run(argv, cwd=self.project, env=self.execution(argv)["environment"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", timeout=60)
        if result.returncode:
            raise RuntimeError(f"Helper failed ({result.returncode}): {result.stdout}")
        return result.stdout

    def freeze(self, destination, payload):
        with tempfile.TemporaryDirectory(prefix="package-", dir=self.staging) as temporary:
            source = Path(temporary)
            for name, value in payload.items():
                data = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else self.records.encoded(value)
                (source / name).write_bytes(data)
            self.records.freeze(self.tree, self.project, source, destination)
        self.records.verify_manifest(self.tree, destination)

    def core(self):
        self.record("proposal.json", {
            "summary": "个人收件箱四分类：从规则基线到可运行的小模型。 " + NOTICE,
            "sections": [
                {"title": "目标", "body": "将短英文消息分为 todo / expense / appointment / other，保留可对任意文本推理的模型与代码。"},
                {"title": "研究路径", "body": "在CPU上运行规则基线与9个朴素贝叶斯变体，探索特征、平滑、增强和先验；父节点只表示方法来源，每次从零拟合。"},
                {"title": "评测边界", "body": "52条训练消息、v1的16条基础样例、v2的24条边界样例和8条对比输入互不重叠。两版均为开发集，示例已暴露，不是独立盲测；只比较同版分数，概率未经校准。"},
                {"title": "选择与使用", "body": "对比规则、词袋和混合增强三种方法对同一条消息的分类结果。选定后可让 Agent 直接用模型处理新消息。下一步需要真实脱敏样本和独立评测；当前选择不代表已经部署或验收。"},
            ],
            "examples": [{"id": "task", "input": "Please send the invoice copy", "expected_output": "todo"},
                         {"id": "receipt", "input": "Receipt for groceries total 18 dollars", "expected_output": "expense"}],
            "approaches": [
                {"id": "rules", "title": "关键词规则", "roles": ["baseline"], "rationale": "无额外依赖，检查完整输入输出和评分通路。"},
                {"id": "local", "title": "轻量监督分类器", "roles": ["recommended"], "rationale": "在本地 CPU 比较特征与训练数据干预，保留实际输出。"},
                {"id": "semantic", "title": "语义模型或强语言模型", "roles": ["reference", "challenge"], "rationale": "真实研究可检验语义能力差距。", "limitations": "本演示仅使用标准库与合成数据，不下载权重、不调用 API；此路线未运行，不宣称效果。"},
            ],
            "feasibility": {"verdict": "feasible", "reason": "此微型任务可用Python标准库在本地CPU完成，无依赖下载、网络或付费服务。"},
        }, self.initial["proposal.json"])
        training = rows(TRAIN, "train")
        comparison = [{"sample_id": f"compare-{i:02d}", "input": text} for i, text in enumerate(COMPARISON, 1)]
        seen = set()
        for pool in (training, rows(EASY, "v1"), rows(EDGE, "v2"), comparison):
            inputs = {row["input"].strip().casefold() for row in pool}
            if seen & inputs or len(inputs) != len(pool):
                raise ValueError("Demo sample pools overlap")
            seen |= inputs
        self.raw("data/train.jsonl", jsonl(training))
        self.raw("data/comparison.jsonl", jsonl(comparison))
        for name, source in (("train.py", TRAIN_SOURCE), ("infer.py", INFER_SOURCE), ("evaluate.py", EVALUATE_SOURCE)):
            self.raw("src/" + name, source)
        self.record("resources.json", {"items": [
            {"id": "training", "title": "合成训练消息", "type": "dataset", "status": "ready",
             "path": "data/train.jsonl", "size": f"{len(training)} 条", "monitor": {"kind": "file"}},
            {"id": "comparison", "title": "同输入对比样例", "type": "dataset", "status": "ready",
             "path": "data/comparison.jsonl", "size": f"{len(comparison)} 条", "monitor": {"kind": "file"}},
            {"id": "python", "title": "本地Python", "type": "environment", "status": "ready",
             "version": platform.python_version(), "monitor": {"kind": "python"}},
            {"id": "memory", "title": "当前主机内存", "type": "hardware", "status": "unknown", "monitor": {"kind": "memory"}},
        ]}, self.initial["resources.json"])
        self.record("project.json", {**self.read_json("project.json"), "name": "个人收件箱 · 轻量模型研究", "language": "zh-CN"}, self.initial["project.json"])

    def evaluation(self, version, pool):
        base = f"evaluation/{version}"
        definition = {
            "version": version,
            "description": "基础词汇与明确意图" if version == "v1" else "边界案例：待付款、已扣费、拼写错误、改期与闲聊干扰",
            "rubric": RUBRIC,
            "metrics": [{"id": "accuracy", "label": "准确率", "direction": "maximize"},
                        {"id": "macro_f1", "label": "宏平均F1", "direction": "maximize"}],
            "command": [self.python, "-B", base + "/evaluate.py"],
        }
        # Calibrate byte-identical code outside the project, leaving only one
        # calibration log in the frozen package and no runtime scratch copies.
        with tempfile.TemporaryDirectory(prefix="calibration-", dir=self.staging) as temporary:
            source = Path(temporary)
            (source / "evaluate.py").write_text(EVALUATE_SOURCE, encoding="utf-8")
            (source / "infer.py").write_text(INFER_SOURCE, encoding="utf-8")
            log = self.helper([self.python, "-B", str(source / "evaluate.py"), "--self-test"])
        if self.records.strict(log).get("passed") is not True:
            raise ValueError("Evaluation calibration failed")
        self.freeze(base, {"definition.json": definition, "samples.jsonl": jsonl(rows(pool, version)),
                           "evaluate.py": EVALUATE_SOURCE, "infer.py": INFER_SOURCE, "calibration.log": log})
        previous = self.tree.read("project.json")
        self.record("project.json", {**self.records.strict(previous), "current_evaluation": version}, self.records.digest(previous))

    def experiment(self, number, variant):
        title, parent, hypothesis, changes = variant
        ident = f"exp-{number:03d}"
        base = "experiments/" + ident
        snapshot = base + "/snapshot"
        parameters = {"kind": "naive_bayes", "features": "word", "alpha": 1.0, "ngram_min": 3,
                      "ngram_max": 3, "prior": "uniform", "augmentation": False, "binary": False, **changes}
        self.freeze(snapshot, {"train.py": TRAIN_SOURCE, "infer.py": INFER_SOURCE, "parameters.json": parameters})
        model_path = base + "/model/model.json"
        with self.tree.directory(self.records.parts(base + "/model"), create=True):
            pass
        argv = [self.python, "-B", snapshot + "/train.py", "--data", "data/train.jsonl",
                "--parameters", snapshot + "/parameters.json", "--output", model_path]
        self.record(base + "/config.json", {
            "id": ident, "title": title, "parent_experiment_id": f"exp-{parent:03d}" if parent else None,
            "hypothesis": hypothesis, "method": title, "role": "baseline" if number == 1 else "candidate",
            "model_name": "关键词分类器" if number == 1 else "多项式朴素贝叶斯", "framework": "Python 标准库 · CPU",
            "parameters": parameters, "inputs": [{"path": "data/train.jsonl", "sha256": self.sha("data/train.jsonl")}],
            "snapshot_sha256": self.sha(snapshot + "/manifest.json"), "execution": self.execution(argv),
        })
        self.record(base + "/status.json", {"state": "pending", "updated_at": now()})
        try:
            self.run(base)
            self.records.verify_manifest(self.tree, snapshot, self.read_json(base + "/config.json")["snapshot_sha256"])
            model = self.read_json(model_path)
            if (model["parameters"] != parameters or model["fitted"] != (number != 1)
                    or model["training_sha256"] != self.sha("data/train.jsonl") or model["labels"] != list(LABELS)):
                raise ValueError("Generated model does not match its declared training inputs")
            # The entry point lets evaluations, comparisons and later use call the model the same way.
            self.raw(base + "/model/invoke.json", {"argv": [self.python, "-B", snapshot + "/infer.py", "--model", model_path, "--jsonl"],
                                                  "description": "JSONL {sample_id,input} -> {sample_id,output}"})
            model_hash = self.records.manifest(self.tree, base + "/model")["manifest_sha256"]
            self.finish(base, target={"kind": "local", "path": base + "/model", "sha256": model_hash})
        except Exception as exc:
            self.fail(base, exc)
            raise
        self.models[ident] = {"path": model_path, "target": base + "/model", "sha256": model_hash}
        self.evaluate(ident, "v1" if number <= 5 else "v2")

    def evaluate(self, experiment, version):
        ident = f"eval-{version}"
        base = f"experiments/{experiment}/evals/{ident}"
        evaluation = f"evaluation/{version}"
        model = self.models[experiment]
        argv = [self.python, "-B", evaluation + "/evaluate.py", "--model", model["path"], "--samples", evaluation + "/samples.jsonl"]
        evaluation_hash = self.sha(evaluation + "/manifest.json")
        self.record(base + "/config.json", {"id": ident, "evaluation_version": version,
                    "target_sha256": model["sha256"], "evaluation_sha256": evaluation_hash, "execution": self.execution(argv)})
        self.record(base + "/status.json", {"state": "pending", "updated_at": now()})
        try:
            self.run(base)
            # The evaluator emits only JSON; the runner does not decorate run.log.
            result = self.read_json(base + "/run.log")
            self.records.verify_path_hash(self.tree, model["target"], model["sha256"])
            self.records.verify_manifest(self.tree, evaluation, evaluation_hash)
            sample_rows = self.records.shape(evaluation + "/samples.jsonl", self.tree.read(evaluation + "/samples.jsonl"))
            output_data = jsonl(result["outputs"])
            output_rows = self.records.shape(base + "/outputs.jsonl", output_data)
            expected = [(row["sample_id"], row["input"], row["reference"]) for row in sample_rows]
            actual = [(row["sample_id"], row["input"], row["reference"]) for row in output_rows]
            if actual != expected or any(row["output"] not in LABELS for row in output_rows):
                raise ValueError("Evaluation outputs do not match frozen samples")
            if set(result["metrics"]) != {"accuracy", "macro_f1"} or any(
                    type(value) not in (int, float) or not 0 <= value <= 1 for value in result["metrics"].values()):
                raise ValueError("Evaluation did not produce the declared finite metrics")
            self.record(base + "/outputs.jsonl", output_data)
            self.finish(base, metrics=result["metrics"])
        except Exception as exc:
            self.fail(base, exc)
            raise
        self.evaluations[(experiment, version)] = result

    def analyze(self):
        for number, _ in enumerate(VARIANTS, 1):
            experiment = f"exp-{number:03d}"
            version = "v1" if number <= 5 else "v2"
            result = self.evaluations[(experiment, version)]
            delta = result["metrics"]["macro_f1"] - self.evaluations[("exp-001", version)]["metrics"]["macro_f1"]
            outcome = "baseline" if number == 1 else "keep" if delta > 1e-12 else "discard" if delta < -1e-12 else "inconclusive"
            errors = [row for row in result["outputs"] if row["output"] != row["reference"]]
            summary = (f"{version}：准确率 {result['metrics']['accuracy']:.1%}，宏平均F1 {result['metrics']['macro_f1']:.3f}。"
                       + ("固定规则作为同版比较起点。" if number == 1 else f"比同版 exp-001 的F1 {delta:+.3f}。")
                       + f" 错误 {len(errors)}/{len(result['outputs'])}。")
            if errors:
                row = errors[0]
                summary += f" 例：{row['input']} → {row['output']}，参考 {row['reference']}。"
            if version == "v1" and (experiment, "v2") in self.evaluations:
                retest = self.evaluations[(experiment, "v2")]["metrics"]
                summary += f" 同一模型在v2重测：准确率 {retest['accuracy']:.1%}，F1 {retest['macro_f1']:.3f}；没有再训练，跨版分差不是模型变化。"
            self.record(f"experiments/{experiment}/analysis.json", {"outcome": outcome, "summary": summary})

    def deliver(self):
        samples = [self.records.strict(line) for line in self.tree.read("data/comparison.jsonl").splitlines() if line.strip()]
        outputs, logs = {}, []
        for experiment in DELIVERIES:
            model = self.models[experiment]
            snapshot = f"experiments/{experiment}/snapshot"
            self.records.verify_path_hash(self.tree, model["target"], model["sha256"])
            self.records.verify_manifest(self.tree, snapshot, self.read_json(f"experiments/{experiment}/config.json")["snapshot_sha256"])
            output = Path(self.staging) / (experiment + "-comparison.jsonl")
            argv = self.read_json(model["target"] + "/invoke.json")["argv"] + ["data/comparison.jsonl", str(output)]
            log = self.helper(argv)
            values = [self.records.strict(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
            if ([row["sample_id"] for row in values] != [row["sample_id"] for row in samples]
                    or any(row["output"] not in LABELS for row in values)):
                raise ValueError("Comparison inference did not return all fixed inputs")
            self.records.verify_path_hash(self.tree, model["target"], model["sha256"])
            outputs[experiment] = {row["sample_id"]: row["output"] for row in values}
            logs.append(experiment + "\n" + log)
        self.raw("comparison/run.log", "\n".join(logs))
        self.record("comparison/outputs.jsonl", jsonl([
            {"sample_id": row["sample_id"], "input": row["input"],
             "outputs": {experiment: values[row["sample_id"]] for experiment, values in outputs.items()}} for row in samples]))
        previous = self.tree.read("resources.json")
        items = self.records.strict(previous)["items"]
        for experiment in DELIVERIES:
            path = self.models[experiment]["path"]
            items.append({"id": experiment, "title": self.read_json(f"experiments/{experiment}/config.json")["title"],
                          "type": "model", "status": "ready", "path": path,
                          "size": f"{len(self.tree.read(path)):,} bytes", "monitor": {"kind": "file"}})
        self.record("resources.json", {"items": items}, self.records.digest(previous))
        previous = self.tree.read("project.json")
        self.record("project.json", {**self.records.strict(previous), "deliveries": DELIVERIES}, self.records.digest(previous))

    def generate(self):
        self.preflight()
        self.core()
        self.evaluation("v1", EASY)
        for number, variant in enumerate(VARIANTS[:5], 1):
            self.experiment(number, variant)
        self.evaluation("v2", EDGE)
        # Remeasure the same rule and word models under the new standard, without
        # re-fitting or selecting a winner across incompatible evaluation versions.
        for experiment in ("exp-001", "exp-002"):
            self.evaluate(experiment, "v2")
        for number, variant in enumerate(VARIANTS[5:], 6):
            self.experiment(number, variant)
        self.analyze()
        self.deliver()
        report = self.records.validate(self.tree)
        if not report["valid"] or report["unfinished"]:
            raise ValueError(f"Generated records failed validation: {report}")
        files = set(self.tree.files(""))
        research = {path for path in files if path in self.initial or path.startswith(("data/", "src/", "evaluation/", "experiments/", "comparison/"))}
        return {"project": str(self.project), "experiments": len(self.models), "evaluation_runs": len(self.evaluations),
                "evaluation_versions": ["v1", "v2"], "deliveries": DELIVERIES, "comparison_samples": len(COMPARISON),
                "files": {"research": len(research), "created": len(files - self.initial_files), "total": len(files)},
                "validation": report, "notice": NOTICE}


def generate(project):
    project, records = load_records(project)
    tree = records.Tree(project)
    try:
        # Resolve only the OS temp location (macOS /var is a symlink); never resolve
        # user project paths, which must be rejected rather than silently followed.
        with tempfile.TemporaryDirectory(prefix="tunetune-demo-") as temporary:
            return Demo(project, records, tree, Path(temporary).resolve()).generate()
    finally:
        tree.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Fresh already-installed format-3 project (agents host)")
    args = parser.parse_args(argv)
    try:
        result = generate(args.project)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc), "notice": NOTICE}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
