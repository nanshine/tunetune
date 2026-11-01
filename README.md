# TuneTune

TuneTune 是一个文件驱动的协同研究空间。Agent 通过 Skills 完成研究初始化、评测构建、训练和复盘；用户通过本地界面查看研究进展、比较结果并提交反馈。研究记录保存在项目目录中，界面不直接执行训练。

## 环境要求

- macOS 或 Linux
- Python 3.10+
- 从源码构建需要 Node.js 22.12+

## 快速开始

在仓库根目录构建工具包：

```sh
npm --prefix workspace ci
npm --prefix workspace run build
python3 scripts/build-kit.py
```

安装到独立研究目录并启动（将 `/absolute/my-research` 替换为实际路径）：

```sh
python3 dist/workspace-kit-0.3.0/install-workspace.py \
  --kit dist/workspace-kit-0.3.0 \
  --project /absolute/my-research --name '我的研究'
python3 /absolute/my-research/.workspace/app/workspace.py \
  --project /absolute/my-research --port 0
```

打开终端输出的本地地址即可使用。安装后的研究空间只需 Python 即可运行。

将 `skills/` 中的五个技能目录一起安装到所用 Agent 的技能目录，并告诉 Agent 研究项目目录和工具包位置。使用说明见 [研究空间 Skill](skills/research-workspace/SKILL.md)。
