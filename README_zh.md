<p align="center"><a href="README.md">English</a> · 简体中文</p>

<img src="docs/assets/hero.png" alt="TuneTune" width="100%">

> 人与 Agent 协作的模型研究工作台，为具体问题训练、评测并迭代自己的小模型。

[![CI](https://github.com/nanshine/tunetune/actions/workflows/ci.yml/badge.svg)](https://github.com/nanshine/tunetune/actions/workflows/ci.yml) [![npm](https://img.shields.io/npm/v/dsh-tunetune)](https://www.npmjs.com/package/dsh-tunetune) [![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

## 快速开始

把这句话发给你的 Agent：

```text
按照 https://github.com/nanshine/tunetune/blob/main/INSTALL.md 安装 TuneTune。
```

然后在想开展研究的文件夹里，试着提出一个需求：

```text
用 TuneTune 训练一个能从照片里认出特朗普的小模型，使用公开数据。
```

已经安装？直接说需求即可。也可以按下面的[安装说明](#安装)自行安装。

<!-- 录好真实演示后在这里加入视频，使用同一个需求，并标出实际耗时。 -->

## How it works

说出你希望模型解决的问题，Agent 会调研方法、澄清关键问题，提出研究方向和资源预算供你审阅，然后搭建评测、校准评分并测出基线，再按轮次研究：提出假设、运行实验、分析证据、决定下一步。你可以在工作台的无限实验画布上查看研究，通过提案、评测、资源、计划和验收浮窗了解细节。

![研究流程：需求、提案、评测与基线、循环实验、交付；人参与方向指引、审阅和结果试用。](docs/assets/workflow-zh.svg)

| Skill | 分工 |
|---|---|
| `tunetune-init` | 理解需求、调研路线，提出研究方向和资源上限。 |
| `build-evaluation` | 校准评测，与你核对体现个人判断的参考答案，测量基线。 |
| `run-experiments` | 规划并运行实验，分析结果，验证可交付的本地模型。 |
| `research-workspace` | 串联各阶段、维护研究证据，在同一个工作台里恢复和继续研究。 |

在约定范围内，Agent 会跨轮次继续研究，不需要你逐个批准实验。候选方案随实验计划调整；目标、推荐方向或范围变化时，才修改研究提案。你可以随时改变方向或指出评测问题；评测修改后会建立新版本，并重新测量需要比较的候选。

交付时，你可以在工作台里输入真实案例，对比模型输出，亲自验收。研究也可能因为预算用尽或缺少值得继续的实验而停止，Agent 会解释已达到的效果、未满足的要求和不确定性。模型保留在各自的实验目录中供本地使用，导出或接入其他系统可以另行提出。

**三个原则：**

- **为具体问题做自己的小模型。** 根据问题比较训练、提示、检索等路线；明确提出的训练要求仍然需要通过训练来满足。
- **人决定方向与标准。** 你审阅重要选择和体现个人判断的参考答案，并亲自判断最终结果。
- **先评测，再判断改进。** 与实际测量的基线比较，只交付验证过的本地模型；使用外部 API 和向外传输数据需要授权。

## 安装

为当前应用安装一次，之后可以在不同文件夹里开展研究。工作台需要 macOS / Linux 和 Python 3.10+；Windows 用户可以让 Agent 协助配置 WSL2。面板已构建并包含在安装内容中，不需要自行构建前端。

### Claude Code

```text
/plugin marketplace add nanshine/tunetune
/plugin install tunetune@tunetune
```

### Codex

```sh
codex plugin marketplace add nanshine/tunetune
codex plugin add tunetune@tunetune
```

### DeepSeek Harness

在应用的 **Plugins（插件）** 页面安装 `dsh-tunetune`，它包含所需 skills，并把工作台放在对话旁边，无需再安装一份独立 skills。

使用命令行管理 profile 时：

```sh
dsh plugin --profile <profile> add dsh-tunetune
```

### 其他支持 skills 的 Agent

有 Node.js 时，用下面的命令安装四个 skills，把 `<application>` 换成应用的 skills CLI 标识，例如 `cursor` 或 `opencode`：

```sh
npx skills add nanshine/tunetune --global --agent <application> -y
```

这些应用尚未逐一实测。没有 Node.js 时，可以让 Agent 按照 [INSTALL.md](INSTALL.md) 安装，其中也包含手动安装、初始化和启动工作台的说明。

安装后，在研究文件夹里描述任务即可。每个研究会固定自己的工具，更新已安装的 skills 不会替换已有研究使用的工具。

## Contributing

欢迎[反馈问题](https://github.com/nanshine/tunetune/issues)、分享真实研究案例或提交 PR；修改代码时，请参考仓库的[开发与验证指南](AGENTS.md)。

## License

[Apache-2.0](LICENSE)。
