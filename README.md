# TuneTune

和 Agent 一起，把日常需求逐步做成私有、可用的模型：理解需求 → 研究提案与资源计划 → 校准评测 → 基线与有界实验 → 对比并交付。

Agent 会调查有竞争力的方法，而不止寻找最容易运行的基线；必要时用强模型作质量参照，再判断怎样在你的资源范围内得到实用结果。研究空间用无限实验画布和可拖动的浮窗展示提案、实验方案、资源、评测和验收。需要你判断的内容可以直接在面板里回应：确认或修改提案和实验方案、逐条审阅参考答案、点击运行模型看真实输出。研究记录只由 Agent 写；开始、停止和改变边界仍在 Agent 会话中进行。

## 开始

把下面这句话交给能读取仓库、操作本地文件和运行命令的 Agent，换成自己的需求：

> 用 TuneTune（https://github.com/nanshine/tunetune）帮我做一个能整理客户留言的模型，就在当前文件夹开始。

**Agent：先读 [bootstrap.md](bootstrap.md)，获取兼容的正式发布包，在当前目录安装五个 skills 并直接读取继续，启动研究空间，再使用 `tunetune-init` 延续原始需求。不要自行创建独立子研究目录。**

运行需要 macOS / Linux 和 Python 3.10+。正式发布包包含构建好的面板，普通安装不要求用户克隆源码或准备 Node.js。没有兼容发布包时应说明情况；源码构建仅作为用户明确选择的开发路径，不冒充一句话安装已完成。

Codex 使用当前目录的 `.agents/skills/`，Claude Code 使用 `.claude/skills/`。安装到应用会自动发现的目录后，Agent 直接读取已安装的 skills 继续研究，不需要先让你检查技能列表；只有应用明确需要刷新或你发现 skills 未出现时，Agent 才给出具体操作和续接文字，不让你重新解释需求。其他应用只有经过实际验证后才承诺支持。

已有正式解包目录时，由 Agent 执行：

```sh
python3 /absolute/workspace-kit-0.6.0/install-workspace.py --kit /absolute/workspace-kit-0.6.0 --project /absolute/current-directory --host agents
python3 /absolute/current-directory/.workspace/app/workspace.py --project /absolute/current-directory --port 0 --open
```

Claude Code 使用 `--host claude`。独立研究目录仅在明确选择并处理技能发现范围后使用，不是默认入口。初始研究文件只有 `AGENTS.md`、`project.json`、`proposal.json` 和 `resources.json`，其余目录按需创建。

**0.6.0 仅支持研究格式 4，明确拒绝旧格式和不兼容工具，不自动迁移或覆盖已有研究。** 同版重复安装只补齐缺失文件，保留兼容研究和项目指引。

## 怎样开展研究

四个工作流为 `research-workspace`、`tunetune-init`、`build-evaluation` 和 `run-experiments`。Agent 先读取材料并询问关键用途和判断，按干预手段检索当前可用的模型和方法，调查基线、推荐路线及强质量参照，再给出有证据的提案和资源上限。评测校准时同时测出基线；之后实验按轮次进行，每轮记录在实验方案中。新研究通常在这里确认一次；明确委托且覆盖相应范围时可直接继续。

资源计划说明用途、来源、预计大小和位置，必要时包含数据传出条件与费用上限。确认后会连续准备资源、建立评测并在有限预算内实验，不逐包重复请求许可；如果评测答案取决于你的主观判断（例如标签是否合适），冻结评测前会请你审阅一次。API Key 通过安全设置或环境变量提供，不放进聊天、研究文件或日志。

研究空间展示本地模型与 API 对照的真实结果；在线参照不等于私有本地交付。你可以提供想验收的真实输入，各模型通过统一入口生成的输出会显示在“模型对比”中，评测样例也会标出参考答案是否经过你审阅。环境、下载、缓存和临时文件都放在研究目录内，不满意时删除该目录即可清理。质量参照是待测的强候选，不是保证的效果上限。模型生成的参考答案也需要独立校准。

交付只选择实验内已经验证的本地模型，不自动复制或部署，也不代表你已满意。训练只是改进方式之一；规则基线不能冒充完成了明确的训练需求。资源观察不证明科学可行性，安装成功不保证模型效果，Agent 会说明未满足要求并提出具体下一步。

## 开发与验证

维护者需要 Node.js 22.12+ 和 Python 3.10+：

```sh
npm --prefix workspace ci
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
python3 scripts/build-kit.py
```

生成 `dist/workspace-kit-0.6.0/` 和同名压缩包。已有版本输出不会覆盖，另一次构建使用 `--output /absolute/fresh-output`。分发包含四个同版 skills、共享指南与必要工具、服务和监测工具、最小模板及构建好的面板，不包含开发测试、研究数据、密钥、前端源码和依赖。发布包须另行附在正式 GitHub Release；构建不等于发布。

主要目录：`skills/` 为研究工作流及按需技术参考，`workspace/` 为研究空间，`templates/workspace/` 为最小安装模板，`scripts/` 和 `tests/` 为开发工具及测试。稳定原则见 [docs/principles.md](docs/principles.md)。

## 本地演示

在全新、已安装的项目中运行：

```sh
python3 scripts/create-demo.py --project /absolute/my-research
python3 /absolute/my-research/.workspace/app/workspace.py --project /absolute/my-research --port 0 --open
```

演示使用合成数据验证真实轻量实验的执行和展示，拒绝覆盖已有研究；它证明流程能够运行，不证明真实业务质量，演示生成器与数据不进入发布包。
