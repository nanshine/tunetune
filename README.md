# TuneTune

和 Agent 一起，把一个日常需求逐步做成私有、可用的小模型。从明确目标、寻找资源和准备例子开始，再建立评测、尝试训练、查看结果。

面板用于只读查看研究资料、进展和结果对比，唯一保留的写入是直接编辑项目名称。目标与资源补充、评测问答、候选与实验意见、研究复盘，以及验收输出生成请求、偏好和验收决定，都在 Agent 客户端沟通，不在面板提交。研究资料与历史反馈记录继续保留供 Agent 读取；Agent 可按会话记录必要决策证据，但意见不等于自动执行授权。

## 开始

把这句话交给可以读取仓库、操作本地文件和运行命令的 Agent，将需求换成你自己的：

> 用 TuneTune（https://github.com/nanshine/tunetune）帮我做一个能整理客户留言的小模型，就在当前文件夹开始。

**Agent：请读取 [bootstrap.md](bootstrap.md)，获取正式发布包，在当前目录准备工作空间、接入 skills、启动并打开面板，然后使用 `tunetune-init` 与用户明确方向。**

用户无需克隆源码、构建前端或手动安装 skills。运行环境为 macOS / Linux 和 Python 3.10+，Agent 会检查环境；模型与训练依赖按需要准备。尚未发布 Release 时，正式的一句话安装入口暂不可用。

## 仓库结构

- `bootstrap.md`：Agent 获取发布包并开始项目的入口。
- `skills/tunetune-init/`：澄清方向、了解资源、形成开放提案。
- `skills/research-workspace/`：共享文件契约和记录工具。
- `skills/build-evaluation/`、`skills/train/`、`skills/review/`：现有评测、训练和复盘流程。
- `workspace/`：面板源码和本地文件服务。
- `templates/workspace/`：最小项目文件。
- `scripts/`、`tests/`：打包安装工具与测试。

项目文件保存在用户当前目录，skills 默认放在 `.agents/skills/`，面板放在 `.workspace/app/`；目标和资源直接由文件驱动展示。

## 开发与发布

维护者使用 Node.js 22.12+ 和 Python 3.10+ 构建，最终用户只需 Python：

```sh
npm --prefix workspace ci
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
python3 scripts/build-kit.py
```

构建生成一个 `workspace-kit-<version>.tar.gz`，包含同版 skills、文件工具、项目模板和预构建面板。将它附加到仓库的正式 GitHub Release，入口即可发现该版本。重复构建使用 `--output /absolute/fresh-output`；发布前应在空目录验证安装和面板启动。

开发时可以直接用解包目录的 `install-workspace.py --kit <bundle> --project <project>` 安装，再运行 `python3 <project>/.workspace/app/workspace.py --project <project> --port 0 --open`。
