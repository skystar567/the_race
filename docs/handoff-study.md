# 问答、个人笔记与主动拓展交接

任务 04、05、06、11 基于 main `588cec5` 集成成员 B 的 `6077ebf`、`3f85227`，并修复版本、来源和编辑并发问题。审核及验收见[成员交付审核](review-member-deliveries.md)。课程资料、知识任务及发布接口沿用 A 的实现，不清库。

## 界面使用

1. 导入 Markdown 并完成至少一次知识整理后，进入「知识图谱 → 课程提问」。默认问答范围包含当前课程所有已导入资料，包括尚未整理的部分；可选整份资料、章节或两者的并集。
2. 从知识点发起提问会设置焦点，焦点不缩小允许检索的范围。清除焦点影响下次提问，保留范围及正在生成的回答。回答完成后可打开原文，或保存为个人笔记。
3. 「个人笔记」中可预览、编辑、保存 Markdown。知识点也提供生成笔记入口；不需要模型的手写笔记可直接新建。
4. 主动点击拓展解释才调用资料外生成。模型补充单独展示，保存为笔记后仍带标记，不进入课程知识。

查看旧记录无需模型凭据。问答、生成笔记及拓展需要后端凭据，所有模型继续使用现有 `DeepSeek` 适配器与 `deepseek-flash`；交互调用关闭思考。

## 公开 HTTP 契约

以下路由均以 `/api/courses/{course_id}` 开头。所有来源标识验证课程归属。

| 方法与路径 | 输入／结果 |
| --- | --- |
| `POST /answers/stream` | `question`，可选 `version_id`、`focus_concept_id`，`material_ids`、`chapter_ids`；SSE `start`、`delta`、`done` |
| `GET /answers` | 最近回答摘要；可选 `limit` |
| `GET /answers/{answer_id}` | 正文、状态、固定版本、范围、引用、关联概念 |
| `GET /answers/{answer_id}/sources/{snippet_id}` | 回答当时冻结的原文、位置及渲染内容 |
| `GET /notes` | 当前课程个人笔记摘要 |
| `POST /notes` | 手写笔记 `title`、`body_md` |
| `POST /notes/generate` | `source_type: concept/answer/expansion`、`source_id`，可选 `title`、`version_id` |
| `GET /notes/{note_id}` | `body_md`、`html`、引用、`version_id`、`revision`、`expansion`、检查提示 |
| `PUT /notes/{note_id}` | `title`、`body_md`、当前 `revision`；冲突返回 409 |
| `GET /notes/{note_id}/sources/{snippet_id}` | 笔记对应的历史原文 |
| `POST /expansions` | `answer_id` 或 `concept_id`，可选 `question`、`version_id` |
| `GET /expansions/{expansion_id}` | `status`、`text`、错误字段及 `origin: model_expansion` |

界面必须传当前显示的 `version_id`，不能在操作时悄悄取最新版本。省略时后端为新操作选择当前版本；历史回答和拓展作为来源时，必须沿用其版本，显式传入不同版本返回 422。没有首次发布版本时，问答返回 409。

一次回答固定概念目录版本，并冻结当次实际检索到的原文及位置。问答范围与知识整理范围分别维护：未整理原文仍可被引用。因此应使用每条引用的 `source_url`，不能假设它一定存在于 `/knowledge/versions/...`。旧格式回答没有冻结数据时，按其历史知识版本读取。笔记来源为回答时使用该回答冻结的依据。

SSE 的 `start` 返回回答 ID、版本、范围和焦点，`delta` 是未完成正文，`done.answer` 才是持久终态。终态可能是 `completed`、`insufficient`、`interrupted`、`citation_failed` 或 `failed`；存在引用不等于任意结论已获语义证明。中止、连接失败或非法引用不能显示完成。检索没有命中只说明本次检索不足，不证明教材不存在相应知识。

拓展接口即使 HTTP 201 也可能返回 `status: failed`，调用方必须检查业务状态。只有完成的回答或拓展能生成对应笔记。拓展禁止伪造 `snippet:` 引用，正文及其笔记始终保留 `> 模型补充（超出课程资料）`。

## 编辑与更新

个人笔记是独立数据，不由知识发布改写。保存使用乐观修订号；409 保留本地草稿，用户明确重载后才替换。保存期间继续输入的内容不会被较早响应覆盖；切课程、切笔记及慢读取均有请求生命周期保护。

新知识发布后，比较相关知识点的定义、别名、页面、出处、冲突及待核对状态，决定是否提示检查。回答笔记通过引用片段关联概念；同一原文段落对应多个概念时，提示粒度可能较宽。提示不自动调整正文，手写笔记不因发布新版本统一标成过期。原文和历史版本仍保留。

新增 SQLite `answer`、`note`、`expansion` 数据；已有 B 格式回答表补加 `sources_json`、`context_json` 字段。迁移是增补，不重写原文或知识快照；测试覆盖旧结构升级。

前端位于 `web/features/questions`、`notes`、`expansions`，共享来源弹窗位于 `web/shared/study.tsx`。App 保留工作区实例以保存图谱位置；课程切换按课程重新挂载。

## 后续成员接入

C 的纠错仍须通过受控知识流程，分别记录任务执行与问题解决情况；不能通过修改笔记或覆盖原文实现纠错。导出必须收齐回答笔记的冻结依据、历史版本依据、个人修改和拓展标记；只遍历当前知识片段不足以导出旧笔记。参见[成员 C 验收准备](member-c/README.md)。
