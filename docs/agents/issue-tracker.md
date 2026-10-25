# Issue tracker: Local Markdown

本项目的规格与任务保存在 `.scratch/`，无需远程 issue 服务。

## Conventions

- 每项功能使用一个目录：`.scratch/<feature-slug>/`。
- 完整规格保存为 `.scratch/<feature-slug>/spec.md`。
- 实现任务逐项保存为 `issues/<NN>-<slug>.md`，从 `01` 编号，每个任务一个文件。
- 规格和任务顶部使用 `Status:` 记录分诊状态，取值见 `triage-labels.md`。
- 评论和讨论追加到文件末尾的 `## Comments` 下。
- 更新已有规格或任务时修改原文件，避免创建重复副本。

## Publish and fetch

技能要求“发布到 issue tracker”时，创建或更新上述本地文件，并返回文件链接。
技能要求“获取任务”时，读取给定路径；仅提供编号时，在对应功能目录中定位。
分诊状态不表示功能已经实现或验收通过。

## Wayfinding operations

以下约定仅用于 wayfinder 的探索任务：

- 地图保存为 `.scratch/<effort>/map.md`，包含 Notes、Decisions-so-far、Fog。
- 子任务保存为 `issues/NN-<slug>.md`，正文包含待解决问题。
- `Type:` 使用 research、prototype、grilling 或 task。
- 待处理任务保持未认领；开始工作前保存 `Status: claimed`，解决后保存 `Status: resolved`。
- `Blocked by: NN, NN` 记录依赖；所有依赖 resolved 后才可认领。
- 按编号选择尚未解决、未被阻塞且未认领的任务。
- 解决时追加 `## Answer`，并将结论摘要及链接写入地图的 Decisions-so-far。
- claimed/resolved 是探索任务的执行状态，不替代普通规格与实现任务的分诊标签。
