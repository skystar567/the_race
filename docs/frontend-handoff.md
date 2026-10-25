# 成员 A：前端拆分与资料接口交接

这次完成三人协作计划中的共享前端拆分。任务 01 的课程创建、导入、目录、阅读、来源弹窗和下载继续可用；任务 03 现已接入真实知识接口，实现多章节范围、图谱视图和位置保留；新增约定见[任务 03 交接](handoff-ticket-03.md)。

本轮已执行的检查和两路审查结论见[验证记录](verification-a-frontend.md)。

## 文件职责

| 位置 | 内容 | 维护约定 |
| --- | --- | --- |
| `web/main.tsx` | React 启动入口 | 不在这里继续增加业务状态 |
| `web/app/App.tsx`、`app.css` | 课程列表、当前课程、创建课程、整体布局 | A 负责接入各功能和课程切换 |
| `web/features/materials/` | 资料列表、上传、章节、阅读、原文弹窗及独立样式 | A 负责；其他功能通过资料接口读取数据 |
| `web/shared/Icon.tsx`、`Modal.tsx` | 已有多处使用的图标与弹窗 | 共享改动由 A 协调 |
| `web/style.css` | 字体、按钮、表单、提示与空状态等公共样式 | 新功能的专有样式放在自己的目录 |
| `web/api.ts` | 当前课程、资料的类型，HTTP 请求及资料 URL 工具 | 保持既有调用可用；新业务接口写在各功能目录 |

B 的图谱已集成在 `web/features/knowledge/`，后续问答、笔记分别放在 `questions/`、`notes/`；C 将路线放在 `routes/`，纠错和导出分别放在 `feedback/`、`export/`。这些目录按功能实际开发时创建。各自提交入口模块及所需数据说明，由 A 在 `App.tsx` 接入。

## 当前模块接口和状态约定

`MaterialsWorkspace` 接收 `course` 与 `onMaterialCountChange(courseId, count)`。每次成功读取列表及成功导入后，通知外壳同步该课程的资料数量；外壳用 `useCallback` 保持回调稳定。资料列表、当前资料、章节、阅读模式、来源弹窗、加载状态与错误由模块内部管理。

外壳以 `key={course.id}` 挂载资料模块。切换课程会卸载旧模块、取消旧读取与上传请求，并创建新课程的状态。请求取消后不得继续更新界面或通知外壳。取消 HTTP 请求不保证撤销后端已经保存的资料，重新打开原课程时以接口返回的数据为准。

创建课程弹窗独立保存名称、提交状态和错误，不读取资料上传错误。资料专有 CSS 限定在 `.materials-workspace` 内，避免影响后续图谱、问答和路线的同名元素。

后续功能也应按课程隔离状态和未完成请求。图谱在同一课程中打开详情、来源或问答时，需要保留图谱实例或显式保存并恢复视口；不能把“切换课程时重置”套用于“同一课程打开详情”。任务 02 图谱现已接入 `web/features/knowledge/`；详情与来源按当前选择取消过期请求。

## B、C 现在可以调用的资料接口

启动应用后可以在 `/openapi.json` 读取 OpenAPI 描述。以下路径均相对于当前本机后端，标识来自真实响应，不使用文件名代替标识。

| 操作 | 方法与路径 | 返回或约定 |
| --- | --- | --- |
| 列出课程 | `GET /api/courses` | 课程数组，含 `id`、`name`、`material_count` |
| 创建课程 | `POST /api/courses` | JSON 请求体 `{"name":"操作系统"}`；成功为 201 |
| 列出资料 | `GET /api/courses/{course_id}/materials` | 当前课程的资料数组 |
| 导入 Markdown | `POST /api/courses/{course_id}/materials?filename=教材.md` | 请求体是 UTF-8 文件原始字节，不是 JSON 或 multipart；成功为 201 |
| 读取资料与章节 | `GET /api/courses/{course_id}/materials/{material_id}` | 资料元信息、`chapters`、`fragment_count`、`missing_image_count` |
| 读取原文片段 | `GET /api/courses/{course_id}/materials/{material_id}/fragments` | 全部片段；可加 `chapter_id` 查询参数限制到一个章节及其下级章节 |
| 下载原文件 | `GET /api/courses/{course_id}/materials/{material_id}/raw` | 与上传内容一致的原始字节，响应为下载文件 |

章节包含 `id`、`title`、`level`、`parent_id`、`start_line`、`end_line`。片段包含 `id`、`material_id`、`chapter_id`、`start_line`、`end_line`、`kind`、`markdown`、`missing_images`，HTTP 读取时另附用于阅读的 `html`。

使用规则：

- 路径中的课程和资料必须匹配；资料、课程或所选章节不存在时返回 404。前端编码路径和查询参数，不能拼入未转义的文件名。
- 行号从 1 开始，起止行均包含在内，以实际上传文件的 CR/LF 行边界计算。样本文件的行号与整本教材的行号不同。
- 同一次导入的章节及片段标识重启后保持不变。重新导入相同文件会生成新的资料标识，不能假设跨导入的标识相同。
- 父章节范围包含下级章节。选中父章节后，不要再以 `fragment.chapter_id === parentId` 丢掉属于下级章节的片段。标题之前的片段可以没有章节。
- 模型整理使用 `markdown` 和程序提供的片段标识；`html` 仅用于阅读。模型不能自行生成“真实”行号或页码。
- 当前资料状态只有 `imported`，不代表已经生成知识。知识发布状态由任务 02 的知识模块维护。
- 大于 20 MB 返回 413；错误扩展名、空内容或无效 UTF-8 等返回 422。HTTP 错误的 `detail` 可能是字符串或验证错误数组，前端已有 `request` 负责展示可读错误。

后端同进程需要资料时，可通过 `campus.materials.Materials` 的公开业务方法读取，保留课程归属校验；不要直接读写它的数据表或原文文件目录。

## 任务 02 需要提前交接的知识接口

以下接口现已由任务 02 实现，具体路径与结构见[任务 02 交接](handoff-ticket-02.md)：

1. 按课程读取已发布知识，以及固定读取指定知识版本的方法。
2. 章节、知识点、三种关系、关系方向、资料依据或推断标记。
3. 稳定知识点标识、跨章节归属、知识页面与原文片段引用。
4. 整理范围、任务身份、进度、失败原因和成功发布结果。
5. 没有已发布版本、部分范围未整理、请求版本不存在时的返回行为。

03 分支已完成多章节范围和图谱浏览，验证见[任务 03 记录](verification-ticket-03.md)；合入 main 后，A 的 08、B 的 04 和 C 的 07 可并行。模拟数据可用于局部准备，验收仍需真实教材、真实接口和已发布知识。

## 验证方式

沿用已确认的公开 HTTP 接口和真实浏览器作为测试入口，不测试组件私有状态或直接查询数据库。

```sh
npm run typecheck
npm run build
.venv/bin/python -m pytest
sh scripts/start.sh --data-dir /tmp/campus-browser-check
# 另一个终端，先按 README 安装浏览器检查依赖
.venv/bin/python scripts/check_browser.py --sample 'materials/samples/计算机操作系统（第四版）_第2章至2.1.1节.md'
```

浏览器检查覆盖导入错误不出现在创建课程弹窗、两门课程分别导入资料，以及延迟原文响应期间切换课程后旧内容不覆盖当前课程。另检查上传已保存但响应延迟时切换课程：返回原课程后能读取已保存资料，侧栏数量与重新读取的资料列表一致。延迟检查仍读取真实后端响应，只控制浏览器收到响应的时机。
