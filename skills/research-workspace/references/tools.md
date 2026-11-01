# 确定性文件工具

工具为本 Skill 内的 `scripts/records.py`，仅需 Python 3.10+ 和 POSIX（macOS/Linux）标准库；不会执行研究命令、启动服务或管理进程。先从实际加载的 Skill 位置确定脚本绝对路径，以下以 `$RECORDS`、`$PROJECT` 代表已确定的真实路径，不猜全局安装目录。

## 接手与校验

```sh
python3 "$RECORDS" validate --project "$PROJECT"
python3 "$RECORDS" hash --project "$PROJECT" --path goal.json
```

validate 输出 JSON：`valid/errors/warnings/unfinished/unhandled_feedback`。errors 为格式、引用或可核验摘要错误；warnings 为历史固定证据缺失、外部位置未核验、反馈过时等；unfinished 只列未完成执行，不说明进程是否存活。deferred/question 仍待跟进，多份 handled 无明确顺序时也保守列入待人工核对，不猜最后决定。退出码 0 表示没有 errors，仍要阅读其他字段；失败退出 1，命令参数错误退出 2。

检查包括核心文件字段、ID/状态/时间、有限指标、现有 manifest 文件集合及哈希、目标修订/实验/产物/评测/发布引用、成功记录是否有产物或输出。不是完整 JSON Schema 引擎：领域参数、评分语义、样例覆盖、外部资源、用户授权、真实进程以及科学结论仍由 Agent 核验。旧格式 1 缺少扩展固定证据仅警告，不替旧实验补造输入。校验只读取文件，不创建锁或更改状态；可能读到正在发布的中间文件，重新检查后再行动。

## 排他创建与条件更新

先将完整记录准备在项目外的临时输入文件中，再发布：

```sh
python3 "$RECORDS" write --project "$PROJECT" --path assessments/a1/config.json --input /absolute/prepared-config.json --create
python3 "$RECORDS" write --project "$PROJECT" --path goal.json --input /absolute/prepared-goal.json --expected-sha256 "$PREVIOUS_SHA256"
```

两种模式必须且只能选一种。create 永不覆盖；expected 模式在协作锁内比对旧摘要，只允许已约定的可变记录。JSON 禁止重复键和非有限数，JSONL 校验逐例字段及唯一 sample_id。write 做本记录结构检查，不保证全项目引用已写齐，发布最终状态前后分别执行 validate 并人工检查依赖。

- goal 修改必须递增 revision 一位，工具先保存 `history/goals/<旧revision>.json`。
- review/analysis 更新自动保存唯一历史文件，路径分别为 history/reviews 和 history/analyses。
- config、artifacts、result、release、原始反馈、handled 都不能更新；训练终态 status 不再修改。assessment result 存在后不再修改中间 status。
- write 只写列明的研究记录，不编辑任意工程源码；评测草稿的代码、数据等仍用现有编辑工具准备，使用 freeze 固定。
- 锁位于 `.workspace/runtime/records.lock`，冲突立即失败，不删除或抢占锁；文件保持存在是正常现象，锁随进程释放。目标路径拒绝 `..`、绝对路径和符号链接，通过 dir_fd 与 O_NOFOLLOW 防止目录链接穿越。
- 历史保存和目标更新并非跨文件事务；中断后先核对实际内容，相同旧目标历史可复用，冲突历史不能覆盖。协作锁不能阻止编辑器或不遵守锁的程序并发改写。

## 快照与冻结

```sh
python3 "$RECORDS" freeze --project "$PROJECT" --source /absolute/prepared-code --path experiments/e1/snapshot
python3 "$RECORDS" freeze --project "$PROJECT" --source /absolute/prepared-evaluation --path evaluation/versions/v1
```

源目录必须是非空普通文件树，不包含 manifest.json、符号链接或特殊文件，也不能与目标重叠。评测源必须含 version 对应目标的 definition.json；先在独立准备目录整理该版本内容，不为冻结而改写旧发布版本。

工具读取源内容，在新目标目录排他创建各文件，最后写 manifest.json；目标存在即拒绝，不覆盖、不自动删残留目录。整个目录不是原子事务，manifest 未出现表示尚未完整发布，中断后保留证据并使用新目标 ID。仅对源代码、配置、小型评测包使用：当前实现会在内存中暂存内容，大型数据和模型保留外部引用，不用此工具复制。

manifest 固定实际复制字节，不能证明源目录采集期间无人修改；freeze 前协调唯一写入者，完成后核验计划采用的文件和摘要。freeze 不设置只读权限、不修改源文件权限；复制时保留可执行位，但不继承特殊权限。它不更新 current_evaluation，不自动创建实验、不训练；只有内容校验完成且有授权时才切换当前评测。

## 分发与依赖

五个 Skills 整套分发，保持兄弟目录；各业务 Skill 显式引用基础 Skill，不假定宿主自动加载依赖。构建工具将 records.md 的原样副本放入 kit 的 template/research-contract.md；研究项目面板只携带自己的分发文件，运行时不 import 本工具或读取全局技能目录。协议演进先修改唯一原稿，再验证构建副本一致；已有项目协议不随技能升级偷偷覆盖。
