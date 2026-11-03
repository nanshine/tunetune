# TuneTune

和 Agent 一起，把日常需求逐步做成私有、可用的模型：理解需求 → 研究提案与资源计划 → 校准评测 → 基线与有界实验 → 对比并交付。

Agent 会调查有竞争力的方法，而不止寻找最容易运行的基线；必要时用强模型作质量参照，再判断怎样在你的资源范围内得到实用结果。研究空间用无限实验画布展示提案、资源、评测和真实输出，它只读观察研究，唯一的写入是修改项目名称。问题、授权和决定都留在 Agent 会话。

## 开始

把下面这句话交给能读取仓库、操作本地文件和运行命令的 Agent，换成自己的需求：

> 用 TuneTune（https://github.com/nanshine/tunetune）帮我做一个能整理客户留言的模型，就在当前文件夹开始。

**Agent：先读 [bootstrap.md](bootstrap.md)，获取兼容的正式发布包，在当前目录安装并验证五个 skills 可用，启动研究空间，再使用 `tunetune-init` 延续原始需求。不要自行创建独立子研究目录。**

运行需要 macOS / Linux 和 Python 3.10+。正式发布包包含构建好的面板，普通安装不要求用户克隆源码或准备 Node.js。没有兼容发布包时应说明情况；源码构建仅作为用户明确选择的开发路径，不冒充一句话安装已完成。

Codex 使用当前目录的 `.agents/skills/`，Claude Code 使用 `.claude/skills/`。文件安装与 skills 出现在应用中的列表是两项检查；若需要刷新或重开会话，Agent 应给出具体操作和续接文字，不让用户重新解释需求。其他应用只有经过实际验证后才承诺支持。

已有正式解包目录时，由 Agent 执行：

```sh
python3 /absolute/workspace-kit-0.5.0/install-workspace.py --kit /absolute/workspace-kit-0.5.0 --project /absolute/current-directory --host agents
python3 /absolute/current-directory/.workspace/app/workspace.py --project /absolute/current-directory --port 0 --open
```

Claude Code 使用 `--host claude`。独立研究目录仅在明确选择并处理技能发现范围后使用，不是默认入口。初始研究文件只有 `AGENTS.md`、`project.json`、`proposal.json` 和 `resources.json`，其余目录按需创建。

**0.5.0 仅支持研究格式 3，明确拒绝旧格式和不兼容工具，不自动迁移或覆盖已有研究。** 同版重复安装只补齐缺失文件，保留兼容研究和项目指引。

## 怎样开展研究

五个工作流为 `research-workspace`、`tunetune-init`、`build-evaluation`、`run-experiments` 和 `explore`。Agent 先读取材料，校准关键用途和判断，调查基线、推荐路线及强质量参照，再给出有证据的提案和具体资源计划。新研究通常在这里确认一次；明确委托且覆盖相应范围时可直接继续。

资源计划说明用途、来源、预计大小和位置，必要时包含数据传出条件与费用上限。确认后会连续准备资源、建立评测并在有限预算内实验，不逐包重复请求许可。API Key 通过安全设置或环境变量提供，不放进聊天、研究文件或日志。

研究空间展示本地模型与 API 对照的真实结果；在线参照不等于私有本地交付。质量参照是待测的强候选，不是保证的效果上限。模型生成的参考答案也需要独立校准。

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

生成 `dist/workspace-kit-0.5.0/` 和同名压缩包。已有版本输出不会覆盖，另一次构建使用 `--output /absolute/fresh-output`。分发包含五个同版 skills、共享指南与必要工具、服务和监测工具、最小模板及构建好的面板，不包含开发测试、研究数据、密钥、前端源码和依赖。发布包须另行附在正式 GitHub Release；构建不等于发布。

主要目录：`skills/` 为研究工作流及按需技术参考，`workspace/` 为研究空间，`templates/workspace/` 为最小安装模板，`scripts/` 和 `tests/` 为开发工具及测试。稳定原则见 [docs/principles.md](docs/principles.md)。

## 本地演示

在全新、已安装的项目中运行：

```sh
python3 scripts/create-demo.py --project /absolute/my-research
python3 /absolute/my-research/.workspace/app/workspace.py --project /absolute/my-research --port 0 --open
```

演示使用合成数据验证真实轻量实验的执行和展示，拒绝覆盖已有研究；它证明流程能够运行，不证明真实业务质量，演示生成器与数据不进入发布包。
