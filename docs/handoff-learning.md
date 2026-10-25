# 学习功能接口交接（任务 04—13）

所有接口都以课程和已发布知识版本为边界；不返回 API Key，不接受前端传入模型密钥。问答与反馈失败不会改变当前已发布版本。

## 问答

- `POST /api/courses/{course_id}/ask`
  ```json
  {"question":"进程是什么？","material_ids":[],"chapter_ids":[],"concept_id":null,"expansion":false,"version_id":null}
  ```
  返回 `status`（`completed` / `completed_with_expansion` / `unverified` / `invalid_citations` / `insufficient`）、`answer`、`citations`（片段、文件名、行号、章节、quote）、`version_id`、`warnings`。回答落库，`GET /api/courses/{course_id}/answers` 可读取。
- `POST /api/courses/{course_id}/ask/stream`：SSE，事件 `delta` → `done` / `error`；`done` 含最终校验状态和引用。前端当前使用普通 JSON 请求；SSE 已由测试覆盖。
- 引用只允许本次检索的当前版本片段；`unverified` 和 `invalid_citations` 不得显示为完成答案。

## 笔记

- `GET/POST /api/courses/{course_id}/notes`
- `GET/PATCH /api/notes/{note_id}`
- `GET /api/notes/{note_id}/health`

笔记正文独立于课程知识；citation 保存 `snippet_id/quote/version_id`。health 只针对引用片段是否仍在当前版本或原文是否变化提示，不判定个人理解对错。

## 路线

`GET /api/courses/{course_id}/route?target=<concept_id>&current=<concept_id>`

返回 `status`（`complete` / `partial` / `blocked`）、`route`、`prior`、`cycles`、`gaps`、`unverified`、`excluded_relations`、`warnings`。只使用 `precedes`；包含和对比不参与排序。

## 导出

`GET /api/courses/{course_id}/export`（可选 `version_id`）返回 zip：

- `knowledge/index.md`、`knowledge/concepts/<id>.md`
- `relations.md`、`notes/index.md`、`notes/<id>.md`
- `sources.md`、`materials/<id>.md`、`materials/README.md`
- `conflicts.md`（有冲突时）、`manifest.json`、`README.md`

导出固定当前版本、笔记和原文内容，不包含其他课程。

## 反馈

- `POST /api/courses/{course_id}/feedback`
  ```json
  {"target_type":"concept","target_id":"<id>","body":"具体问题"}
  ```
- `GET /api/feedback/{id}`
- `POST /api/feedback/{id}/recheck`：从目标引用所在章节发起新的整理任务；候选版本发布后比较页面/定义，返回：
  - `feedback.status`：`open` / `checking` / `resolved`
  - `feedback.resolution`：`changed` / `unchanged` / `failed` / `checking`
  - `task`：任务状态
  - `changed`：是否变化

任务完成不等于问题已修正；`unchanged` 和 `failed` 必须如实显示。反馈不覆盖笔记。

## 契约边界

- 问答与反馈都使用当前已发布版本；候选版本不可读取。
- 追加整理现在允许；`parent_version_id` 指向发布时当前版本，旧版本保留。
- 同名概念只有在名称/别名匹配且定义或证据相近时才复用 ID；否则保留双方并进入冲突记录。
- 没有鉴权，只用于本机单用户 Demo。
