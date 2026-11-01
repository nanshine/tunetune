# TuneTune

文件驱动的协同研究空间。统一名称为 `workspace`（研究空间），按需用“目录、界面、服务”说明具体部分，不再引入另一套产品术语。Agent 通过四个 skills 操作研究文件，界面负责展示与保存用户反馈，不启动训练、不维护业务数据库。

## 基础框架

- `workspace/`：React + TypeScript + Vite、只读 React Flow 谱系、资料抽屉、实验与独立评测详情、发布对照和反馈；Python 标准库提供本地文件通道。
- `templates/workspace/`：不含虚构数据的最小模板；`AGENTS.md` 定义格式 1 的字段、版本固定和写入规则。
- `skills/`：init、build-evaluation、train、review。技能是 Agent 的操作指引，不是执行引擎。
- `scripts/`：预构建打包与一次性安装工具，不是研究业务 CLI。
- `tests/`：同步、反馈安全、分发隔离与安装保护测试。

## 构建与使用

开发需要 Node.js 22.12+ 和 Python 3.10+；当前文件安全实现面向 macOS/Linux（POSIX），Windows 尚未支持。研究项目运行只需要 Python，不需要 Node、产品源码或前端依赖。

从产品根目录执行：

```sh
npm --prefix workspace ci
npm --prefix workspace run build
python3 scripts/build-kit.py
```

生成 `dist/workspace-kit-0.2.0/`、对应 `.tar.gz` 及独立的 `skills-0.2.0.tar.gz`。已有同版本输出不会被覆盖；再次打包可用 `--output /absolute/fresh-output` 指定新目录。分发不包含 design、reference、源码或 node_modules。

0.2.0 起统一使用“研究空间”及 `workspace` 命名：展示设置为 `workspace.json`，预构建文件位于 `.workspace/`。旧版分发已移除；安装器遇到旧目录或旧展示配置会在写入前停止，不自动迁移或创建并行配置。

将工具包安装到独立研究目录（替换下面的绝对路径）：

```sh
python3 dist/workspace-kit-0.2.0/install-workspace.py \
  --kit dist/workspace-kit-0.2.0 \
  --project /absolute/my-research --name '我的研究'
python3 /absolute/my-research/.workspace/app/workspace.py \
  --project /absolute/my-research --port 0
```

打开脚本打印的本地地址；Ctrl+C 关闭研究空间服务不影响独立训练。已有业务文件只检查并保留，不覆盖；冲突会在写入前报告。安装器核验内容哈希，但发布者可信性需要单独确认。研究空间工具包升级和格式迁移尚未实现。

四个 skills 分别安装到所用 Agent 支持的技能目录；本仓库不自动修改全局配置。告诉 Agent 项目目录和可信工具包位置，先用 init 整理目标，再构建评测、训练、复盘。字段示例与规则见 `templates/workspace/AGENTS.md`。

## 前端开发

先安装一个研究目录；两个终端分别启动文件服务与 Vite：

```sh
python3 workspace/workspace.py --project /absolute/my-research \
  --assets workspace/dist --port 8765
npm --prefix workspace run dev -- --port 5173
```

Vite 把 `/api` 文件通道代理到 8765；这只是浏览器与本地文件的桥接，不供 Agent 执行研究业务。生产访问使用预构建资源和 Python，不需要 Vite。

## 验证

```sh
npm --prefix workspace run build
npm --prefix workspace test
python3 -B -m unittest discover -s tests -v
```

覆盖畸形文件保留最后快照、版本冲突、反馈幂等、目录穿越和符号链接、原始回答不可覆写、项目隔离、完整清单校验及搬迁后的独立启动。测试数据只在临时目录生成，不混入模板或分发。

## 当前边界

每 2 秒读取约定文件；失败保留最后可用内容。文件刷新和视图切换保留当前会话内的草稿、选择和画布视口；刷新整个网页不保存未提交草稿。反馈保存后仍待 Agent 处理，不唤醒会话或自动执行。训练状态仅代表最后记录，硬件状态默认未知。

这是可运行基础框架，不是完整产品：尚无资源采集器、自动提醒、离线导出、高级曲线、批量标注编辑器或大数据分页；Markdown 当前按安全纯文本展示。单文件上限 4 MiB（日志展示最后 64 KiB）、快照上限 32 MiB / 2000 个文件，超限明确报同步错误；大型数据和模型保留外部引用。四个技能尚未做模型级行为基准评测。
