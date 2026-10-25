# 任务 04 交接：带依据问答（04 → 05／06／11）

日期：2026-10-25。负责人：成员 B。实现基于任务 02 的版本化知识；成员 A 的 03 章节导航仍未实现。

## 1. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/courses/{course_id}/answers/stream` | 提问并返回 SSE |
| GET | `/api/courses/{course_id}/answers` | 最近回答（默认 20 条） |
| GET | `/api/courses/{course_id}/answers/{answer_id}` | 回答详情、引用、HTML |

请求：

```json
{
  "question": "进程和线程有什么区别？",
  "material_ids": [],
  "chapter_ids": [],
  "focus_concept_id": null
}
```

- `material_ids` 与 `chapter_ids` 为空表示当前已发布知识版本覆盖的全部内容；两者可同时给出，取并集。
- 所选资料/章节必须属于该版本，否则 422；课程尚未发布知识返回 409。
- `focus_concept_id` 只是提问焦点，不限制证据范围；不属于该版本返回 422。

## 2. SSE 事件

```text
event: start
data: {"answer_id":"...","version_id":"...","scope":{"label":"全部已整理内容","fragment_count":7,...},"focus":null,"evidence_count":7,"missing_image_count":0,"resolution":"keyword"}

event: delta
data: {"text":"进程是..."}

event: done
data: {"answer":{...完整回答，含 status、citations、html、error_code}}
```

- `resolution`：`keyword`（确定性检索）、`model`（Flash 从目录选择）、`none`（无证据）。
- 客户端中止或流中断后，服务端把回答标为 `interrupted`，已生成文本保留。

## 3. 状态语义

| 状态 | 含义 |
| --- | --- |
| `generating` | 正在生成（通常只在流中短暂出现） |
| `completed` | 正常结束，且至少一条引用通过片段范围校验 |
| `insufficient` | 无证据，或回答没有可核查引用；正文会说明资料不足 |
| `citation_failed` | 回答引用了未提供的片段；不能视为完成 |
| `interrupted` | 连接中断/客户端中止；已显示内容不完整 |
| `failed` | 空输出、模型错误或未预期错误 |

`completed` 只表示结构与引用定位校验通过，**不表示结论在语义上被原文支持**。

## 4. 持久化与版本固定

`answer` 表保存：`id`、`course_id`、`version_id`、`question`、`scope_json`、`focus_concept_id`、`status`、`text`、`citations_json`、`error_code`、`error_message`、`created_at`。

引用项：

```json
{
  "snippet_id": "...",
  "filename": "验收短文（非教材原文）.md",
  "chapter_title": "2.1 进程",
  "start_line": 5,
  "end_line": 5,
  "excerpt": "进程是程序的一次执行。……"
}
```

打开引用使用版本固定接口：

```text
GET /api/courses/{course_id}/knowledge/versions/{answer.version_id}/sources/{snippet_id}
```

新版本发布后，旧回答仍按其 `version_id` 打开当时原文；不会悄悄改指新内容。

## 5. 给 05（个人笔记）

- 从回答生成笔记时，保存 `answer_id`、`version_id`、引用列表和回答状态。
- `citation_failed` / `interrupted` / `failed` 的回答不应作为“已完成依据”写入笔记；可保存草稿，但要保留真实状态。
- 笔记正文由学生编辑；知识更新不能覆盖笔记（ADR 0001）。
- 生成笔记的模型调用继续走统一适配器，统一 `deepseek-flash`。

## 6. 给 06（拓展解释）

- 当前 04 的提示词明确要求默认只给资料内结论；06 需要新增**用户主动启用**的参数（例如 `allow_expansion`），不能默认开启。
- 拓展内容必须在回答与笔记中保留“模型补充”标记，且不能写入课程知识。
- 复用 `answer` 状态机；拓展生成失败/中断要单独显示，不能标为完成。

## 7. 给 11（更新后保留）

- 旧回答的 `version_id` 与引用已持久化；11 需要验证发布期间正在生成的问答仍固定旧版本。
- 笔记保存与发布并发时，笔记正文不能被覆盖；相关依据变化时才提示检查，不是把所有笔记标为过期。
- 依赖 A 的 08 提供新版本发布与变化摘要。

## 8. 已知限制

1. 范围是已发布版本覆盖的内容；未整理的原始资料不参与问答。
2. 无向量检索；中文二字词、别名和一跳图谱邻接先做确定性匹配。
3. 路由可能选择弱相关概念；回答仍须自行说明资料不足，程序不判断语义相关性。
4. SSE 不提供断线续传。
5. 引用合法 ≠ 语义支持；代表问题的人工核对仍未完成（真实教材缺失）。
6. 03 的章节导航由 A 负责；04 没有替代 03 的验收。
