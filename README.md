# TuneTune

和 Agent 一起，把日常需求逐步做成私有、可用的小模型：研究提案 → 校准评测 → 验证基线 → 在有限预算内实验 → 对比并交付。

面板用无限实验画布展示提案、资源、评测样例、实验与模型输出。它只读观察研究，唯一的写入是修改项目名称。问题、执行请求和用户决定都在 Agent 会话中沟通，不需要填写另一套表单。

## 开始

把下面这句话交给能读取仓库、操作本地文件和运行命令的 Agent，换成自己的需求：

> 用 TuneTune（https://github.com/nanshine/tunetune）帮我做一个能整理客户留言的小模型，就在当前文件夹开始。

**Agent：先读 [bootstrap.md](bootstrap.md)，获取正式发布包，在当前目录安装 skills 和面板，启动并打开面板，然后使用 `tunetune-init` 调查需求、形成供用户讨论的提案。**

运行需要 macOS / Linux 和 Python 3.10+。用户不必克隆源码、构建前端或手动安装 skills；模型依赖按研究需要准备。没有正式发布包时，一句话安装暂不可用，不应偷偷改用源码构建。

已有本地解包目录时，可由 Agent 执行：

```sh
python3 /absolute/workspace-kit-0.4.0/install-workspace.py --kit /absolute/workspace-kit-0.4.0 --project /absolute/my-research --host agents
python3 /absolute/my-research/.workspace/app/workspace.py --project /absolute/my-research --port 0 --open
```

Claude Code 使用 `--host claude`。默认 skills 位于 `.agents/skills/`，面板与服务位于 `.workspace/app/`。初始研究文件只有 `AGENTS.md`、`project.json`、`proposal.json` 和 `resources.json`；实验与评测在需要时才创建。文件格式指南只随共享 skill 提供。

**0.4.0 只支持格式 2。旧项目和不兼容工具会被明确拒绝，不会自动迁移或覆盖。** 同版重复安装只补齐缺失文件，保留已有研究和项目指引。

## 能做什么，以及不能保证什么

Agent 会调查可行路线、建立真实可运行的评测、保留基线，并在授权的时间、成本和访问范围内实验。清楚的授权可以覆盖多轮工作，不需要每轮重复批准。资源监测只提供文件存在、内存等有限观察，不能证明数据适合训练。

交付选择指向实验内已经验证的模型，不复制模型，也不代表部署。可以比较同一输入的真实输出；需要独立导出包时再提出。面板不是自动研究调度器，打开页面不代表 Agent 会无限继续。模型可能达不到目标，私有数据访问、训练算力和实际效果也不能由安装成功来保证。

## 开发与打包

维护者需要 Node.js 22.12+ 和 Python 3.10+：

```sh
npm --prefix workspace ci
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
python3 scripts/build-kit.py
```

生成 `dist/workspace-kit-0.4.0/` 和同名 `.tar.gz`。发布包包含五个同版 skills、共享 `records.py` / `run.py`、文件服务及 `monitor.py`、最小模板和预构建静态资源，不包含演示数据、前端源码或依赖目录。重复构建使用 `--output /absolute/fresh-output`，不会覆盖已有产物。将压缩包附在正式 GitHub Release 上即可供安装入口发现。

主要目录：`skills/` 为研究方法与文件工具，`workspace/` 为面板和本地服务，`templates/workspace/` 为最小模板，`scripts/` 和 `tests/` 为工具及测试。稳定产品原则见 [docs/principles.md](docs/principles.md)。

## 本地演示

在一个全新、已安装的项目中运行：

```sh
python3 scripts/create-demo.py --project /absolute/my-research
python3 /absolute/my-research/.workspace/app/workspace.py --project /absolute/my-research --port 0 --open
```

生成器真实执行轻量文本分类实验，展示评测版本、模型重测、代码快照、实验内模型、逐例输出与比较；拒绝覆盖已有研究。它使用合成数据，只证明研究流程能够运行，不证明真实业务质量，也不是大模型微调效果演示。演示生成器和数据都不进入发布包。
