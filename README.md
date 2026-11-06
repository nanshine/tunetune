# TuneTune

和 Agent 一起，把日常需求逐步做成私有、可用的模型：理解需求 → 研究提案与资源计划 → 校准评测 → 基线与有界实验 → 对比并交付。

Agent 会调查有竞争力的方法，而不止寻找最容易运行的基线；必要时用强模型作质量参照，再判断怎样在你的资源范围内得到实用结果。研究空间用无限实验画布和可拖动的浮窗展示提案、实验方案、资源、评测和验收。需要你判断的内容可以直接在面板里回应：确认或修改提案和实验方案、逐条审阅参考答案、点击运行模型看真实输出。研究记录只由 Agent 写；开始、停止和改变边界仍在 Agent 会话中进行。

## 开始

把下面这句话交给能读取仓库、操作本地文件和运行命令的 Agent（Codex、Claude Code 等），换成自己的需求：

> 用 TuneTune（https://github.com/nanshine/tunetune）帮我做一个能整理客户留言的模型，就在当前文件夹开始。

**Agent：按 [INSTALL.md](INSTALL.md) 安装四个 skills，初始化当前目录，启动研究空间，再用 `tunetune-init` 延续原始需求。不要自行创建独立子研究目录。**

运行需要 macOS / Linux 和 Python 3.10+。skills 自带构建好的面板，不需要克隆源码或准备 Node.js；只有用 `npx` 安装时才需要 Node.js。

<details>
<summary>也可以自己先装好 skills</summary>

任意支持 Agent Skills 的应用（一次安装，所有目录可用）：

```sh
npx skills add nanshine/tunetune --global --agent codex
npx skills add nanshine/tunetune --global --agent claude-code
```

Claude Code 插件：

```text
/plugin marketplace add nanshine/tunetune
/plugin install tunetune@tunetune
```

Codex 插件：

```sh
codex plugin marketplace add nanshine/tunetune
codex plugin add tunetune@tunetune
```

装好后在想做研究的目录里说出需求即可，Agent 会用 skill 自带的初始化工具准备这个目录：

```sh
python3 <research-workspace skill>/scripts/init.py --project /absolute/current-directory
python3 /absolute/current-directory/.workspace/app/workspace.py --project /absolute/current-directory --port 0 --open
```

</details>

初始化只补齐缺失文件：研究指引 `AGENTS.md`、`project.json`、`proposal.json`、`resources.json`，以及固定在 `.workspace/app/` 的研究工具和面板。之后更新 skills 不会改动已有研究所用的工具。**0.7.0 仅支持研究格式 4，明确拒绝旧格式和使用其他版本工具的研究，不自动迁移或覆盖已有研究。**

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
python3 scripts/build-skills.py
```

面板构建输出到 `plugins/tunetune/skills/research-workspace/assets/panel/`，与研究工具、模板一起随 skill 分发；`build-skills.py` 把这些文件的哈希写入 `plugins/tunetune/skills/research-workspace/manifest.json`，`--check` 检查它是否最新。构建结果需要提交，因为 `npx skills`、插件和克隆都直接取仓库里的 skills。分发内容是四个 skills 目录，不包含开发测试、研究数据、密钥、前端源码和依赖。

主要目录：`plugins/tunetune/skills/` 为研究工作流、按需技术参考、工具、模板和构建好的面板，所在的 `plugins/tunetune/` 是只含 skills 和插件清单的插件根目录（插件安装会复制整个根目录），根目录的 `.claude-plugin/` 和 `.agents/plugins/` 是指向它的插件市场；`workspace/` 为面板源码，`scripts/` 和 `tests/` 为开发工具及测试。稳定原则见 [docs/principles.md](docs/principles.md)。

## 本地演示

在全新、已初始化的项目中运行：

```sh
python3 plugins/tunetune/skills/research-workspace/scripts/init.py --project /absolute/my-research
python3 scripts/create-demo.py --project /absolute/my-research
python3 /absolute/my-research/.workspace/app/workspace.py --project /absolute/my-research --port 0 --open
```

演示使用合成数据验证真实轻量实验的执行和展示，拒绝覆盖已有研究；它证明流程能够运行，不证明真实业务质量，演示生成器与数据不进入分发内容。
