# 任务 03：章节范围与图谱交接

实现位于 `ticket/03-chapter-scope-navigation`。验证结果见 [任务 03 验证记录](verification-ticket-03.md)。本任务沿用任务 02 的知识快照、知识点和来源接口，不迁移数据库；首次整理仍只创建一个已发布版本，追加整理由任务 08 接入。

## 整理范围接口

`GET /api/courses/{course_id}/knowledge/coverage?version_id={version_id}` 返回该课程全部已导入资料的整理覆盖情况。省略版本时使用当前已发布版本；尚未发布时 `version_id` 为 `null`，全部资料为未整理。不存在的课程、版本或其他课程的版本返回 404。

响应包含 `course_id`、`version_id` 和 `materials`。每份资料保留资料详情字段，`chapters` 中每章保留原章节字段；资料和章节各自增加以下字段：

| 字段 | 含义 |
| --- | --- |
| `status` | `unorganized`（尚未整理）、`partial`（部分已整理）、`organized`（已整理） |
| `organized_fragments` | 已包含在指定知识快照中的原文片段数量 |
| `total_fragments` | 此资料或章节范围内的全部原文片段数量 |

父章节计算时包含下级章节。选中部分章节不能把整份资料标为已整理；后续新导入的资料在旧版本中显示为未整理。覆盖表示片段经过整理流程，不保证模型已找出片段内每个知识点。

此接口的 `status` 是覆盖状态；原有资料接口的 `status: imported` 保持原义。前端类型、标签和 URL 工具位于 `web/features/knowledge/coverage-api.ts`，资料模块也从此处导入。图谱调用时始终带正在展示的 `version_id`，不混入更新版本的范围状态。

## 图谱接入

`KnowledgeWorkspace` 继续负责读取快照、打开知识点和来源，版本化 URL 契约不变。`GraphExplorer` 接收 `snapshot`、`selectedId` 和 `onSelectConcept(id)`；`CoveragePanel` 接收 `courseId`、`versionId`。

- 初次进入显示章节概览，章节按钮或节点可以展开知识点，父章节包括下级章节内容。
- 跨章节视图包含多章节共用知识点，以及连接不同章节知识点的前置、对比关系。不会按章节重新生成知识点身份。
- 全图包含当前已发布范围的全部节点与关系。各视图均能展开文字关系列表，核查方向、资料依据或系统推断、关系理由。
- 包含为章节指向知识点；前置为前项指向后项；对比不表示先后。系统推断使用虚线和文字标记。
- 同一知识版本内保存各视图的缩放、平移和节点位置；课程或知识版本切换时重新建立图谱。不要用打开详情的操作替换整个 `KnowledgeWorkspace`。

B 的任务 04 和 C 的任务 07 应继续通过同一课程、同一已发布版本读取知识点和来源；不要从图谱中的可见节点反推完整知识范围。新增问答、路线入口分别放在 `features/questions/`、`features/routes/`，由外壳接入。路线高亮若需修改图谱接口，应扩展 `GraphExplorer` 的明确输入，不读取其 Cytoscape 私有状态。

## 小样本

任务 03 共享样本及完整教材行号见 [materials/README.md](../materials/README.md)。可导入两个短片段，首次整理时同时选择两个章节；再导入较长片段而不选中，用于核查范围外内容仍为未整理。真实生成数量和关系可能变化，不把受控浏览器夹具当成真实模型结果。
