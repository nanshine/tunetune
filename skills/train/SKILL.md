---
name: train
description: 按明确授权执行研究训练或实验、独立重测已有产物，并记录可追溯结果；用户说“试这个方案”“跑一轮”“用新版评测重测”“在预算内继续实验”或明确指定发布及验收对照时使用。不默认无限探索或自动发布。
---

# 执行、评测与保留证据

输入：格式 1 项目、用户方向或候选、执行范围/预算、可用资源、具体已发布评测。先读项目 `AGENTS.md` 契约，核对 project 格式与 `.workspace/manifest.json` 兼容性，读取目标、资源、当前评测、候选、review 和未处理反馈；启动前重新检查输入及 SHA-256，共享写入冲突先停止合并。

1. 明确本次假设、起点、要了解的问题和停止条件。一次请求只做一次，只有明确授权连续尝试才循环；不要设强制全局最佳、固定候选数或每轮恢复选中版本。必要资源准备须在本次授权内；环境不明先调查并记录时间，不把旧资源状态当实时可用。
2. 新训练用新 `experiments/<id>/`，先保存不可变 config：id、title、parent_experiment_id、goal_revision、具体 evaluation_version，以及实际代码快照、训练数据、起点模型、参数、环境、命令和内容哈希。已有产物只重测时跳过训练，保留原实验，直接建新的 assessment。
3. 用实际终端/训练工具执行，保留日志并按契约写 pending/running。后台运行时记录真实命令、执行标识、日志路径、观察/停止/接手方法；根据执行方式验证会话结束后能否继续。面板不调度进程，runtime 和陈旧 running 都不能证明存活。
4. 训练终止后先保存日志、可用产物及 `artifacts.json` 的 `{items:[{id,path,sha256}]}`，再**最后写最终 status.json**（state、updated_at）。失败或取消也保存真实错误与可用证据；不能因为有目录就宣称成功，不能改写固定输入。
5. 训练成功后安排独立评测：新建 `assessments/<id>/config.json` 固定实验、产物、产物哈希、评测版本和执行条件。验证哈希后执行该版命令。先保存完整 `outputs.jsonl`（sample_id、input、output、可选 reference/scores），再**最后写 result.json**（state、metrics、可选 error、completed_at）。失败时保留训练成功和产物，不填假分数；重试用新 assessment ID，不重训、不覆盖旧结果。
6. 检查逐例输出与同版比较，保存实验 analysis.md 的改善、退步、限制和证据；更新候选需协调单一写入者。新证据修正旧结论时追加或保留历史。按实际修改新增 feedback/handled 记录，原始反馈不动。
7. 仅用户明确指定发布时写新的 `releases/<id>.json`，固定 experiment_id、artifact_id、assessment_ids、notes 及内容标识。需要验收时在新 `acceptance/<id>/` 固定样例版本和 release_ids，真实推理得到 `{sample_id,input,outputs:{release_id:text}}`，输出齐备后最后发布 config。单例偏好和整体验收分别绑定反馈；分数或单例偏好不是整体接受。

输出：实验/评测 ID 与路径、实际状态、日志与产物哈希、同版结果、失败或未完成部分、下一步。多文件不完整时暂停依赖操作；不在研究空间服务实现业务命令、不因反馈提交或建议自动开始下一轮。
