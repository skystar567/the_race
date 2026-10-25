# 任务 02 交接：版本化课程知识（02 → 03／04／07）

日期：2026-10-25。负责人：成员 B。原交付分支：`ticket/02-knowledge-graph-delivery`；集成修复分支：`fix/ticket-02-integration`。

本文固定任务 02 的读取契约与限制，供成员 A 的 03／08／09／10、成员 B 的 04、成员 C 的 07 使用。下面的返回示例来自**受控验收数据**（合成短文 + 脚本化模型响应），不是真实教材，也不是真实 DeepSeek 调用；真实模型短样本验收已补齐，见[集成修复记录](verification-ticket-02-fixes.md)。下方保留受控示例，便于稳定复现接口。

## 1. 版本、状态与读取

- 一次整理任务对应一行 `knowledge_version`，状态为 `candidate`、`published` 或 `failed`。只有 `published` 可以通过公开接口读取。
- `course_knowledge.current_version_id` 是当前版本指针。发布在一个 SQLite 写事务内完成：校验快照 → 写版本 → 切换指针。指针切换前任何失败都不会产生可用知识。
- 读取必须带版本：`GET /api/courses/{course_id}/knowledge?version_id=...`，或先读当前版本再把 `version_id` 固定下来。图谱、知识点页面、原文引用都从同一个快照读取。
- 当前实现只允许**首次构建**。课程已有已发布知识时，创建新任务返回 422；追加整理（08）必须扩展发布逻辑，不能绕过。
- 知识点 `id` 在发布后稳定；同一任务重试生成相同 `id`（以 `course_id` 命名空间 + `task_id` + 本次 key 生成）。**跨版本沿用同一身份是 08／09 的责任**：整合时必须把旧 `concept.id` 带过去，不能重新随机生成。

## 2. HTTP 契约

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/model/status` | 是否已配置后端凭据；不返回密钥 |
| GET | `/api/courses/{course_id}/tasks` | 任务列表，新到旧 |
| POST | `/api/courses/{course_id}/tasks` | 创建首次整理任务，返回 202 |
| GET | `/api/courses/{course_id}/tasks/{task_id}` | 任务状态、步骤、失败原因 |
| POST | `/api/courses/{course_id}/tasks/{task_id}/retry` | 仅失败任务可重试；保留已完成步骤 |
| GET | `/api/courses/{course_id}/knowledge/versions` | 版本列表与当前标记，不含快照正文 |
| GET | `/api/courses/{course_id}/knowledge?version_id=` | 指定版本快照；缺省读当前版本 |
| GET | `/api/courses/{course_id}/knowledge/versions/{version_id}/concepts/{concept_id}` | 知识点页面 + 引用位置 |
| GET | `/api/courses/{course_id}/knowledge/versions/{version_id}/sources/{snippet_id}` | 原文片段 + 渲染 HTML |

### 2.1 创建任务

```http
POST /api/courses/{course_id}/tasks
Content-Type: application/json

{"material_ids": ["98bfe0bf-..."], "chapter_ids": []}
```

`material_ids` 与 `chapter_ids` 不能同时为空。章节必须属于当前课程。单次范围上限 60,000 字符，超出返回 422 并说明实际字符数，不静默截断。成功返回 202 与任务对象（`status: "queued"`，`steps` 六项）。

### 2.2 任务对象（真实失败样例，已截断字段不省略结构）

```json
{
  "id": "9df102df-4433-4833-9679-1cff414de36d",
  "course_id": "f6b591e7-...",
  "status": "failed",
  "selection": {"material_ids": ["2f4e3993-..."], "chapter_ids": []},
  "scope": {"characters": 45, "fragments": 3, "chapters": 2},
  "version_id": null,
  "error_code": "truncated",
  "error_message": "模型输出被截断，请缩小整理范围后重试。",
  "steps": [
    {"name": "ingest", "label": "读取原文与章节", "status": "completed", "attempts": 0},
    {"name": "extract", "label": "抽取知识点与关系", "status": "failed", "attempts": 1},
    {"name": "integrate", "label": "整合概念与关系", "status": "pending", "attempts": 0},
    {"name": "render", "label": "生成知识点页面", "status": "pending", "attempts": 0},
    {"name": "validate", "label": "校验来源与结构", "status": "pending", "attempts": 0},
    {"name": "publish", "label": "发布知识版本", "status": "pending", "attempts": 0}
  ]
}
```

`status: failed` 时 `version_id` 为 `null`，知识读取仍返回 `state: "unpublished"`。任务状态与可用知识状态是两个字段，界面不能只看任务完成。

### 2.3 知道快照（发布样例，节选）

```json
{
  "course_id": "24c66f26-...",
  "version_id": "404bfe41-...",
  "state": "published",
  "selection": {"material_ids": ["98bfe0bf-..."], "chapter_ids": []},
  "summary": {"new_concepts": 2, "updated_concepts": 0, "conflicts": 0},
  "chapters": [
    {"id": "52900fa9-...", "title": "2.1 进程的定义", "level": 2,
     "start_line": 3, "end_line": 6, "material_id": "98bfe0bf-...",
     "filename": "教材节选（受控样本）.md"}
  ],
  "concepts": [
    {"id": "8e7f6971-...", "name": "进程", "aliases": ["Process"],
     "definition": "程序的一次执行……", "page_md": "...",
     "chapter_ids": ["52900fa9-..."], "status": "confirmed", "is_new": true,
     "citations": [{"snippet_id": "80696775-...", "quote": "进程是程序的一次执行。"}]}
  ],
  "relations": [
    {"id": "7d2396dc-...", "kind": "contains", "from_type": "chapter",
     "from_id": "52900fa9-...", "to_type": "concept", "to_id": "8e7f6971-...",
     "origin": "source", "citation": {"snippet_id": "80696775-...", "quote": "进程是程序的一次执行。"},
     "reason": "由原文章节归属确定"},
    {"id": "9997a5c3-...", "kind": "precedes", "from_type": "concept",
     "from_id": "8e7f6971-...", "to_type": "concept", "to_id": "6e050f9d-...",
     "origin": "suggested", "citation": null,
     "reason": "先理解进程这一资源分配单位，再理解线程这一执行单元。"}
  ],
  "fragments": [
    {"id": "80696775-...", "chapter_id": "52900fa9-...", "start_line": 5,
     "end_line": 5, "kind": "inline", "markdown": "进程是程序的一次执行。……",
     "missing_images": 0, "material_id": "98bfe0bf-...",
     "filename": "教材节选（受控样本）.md"}
  ]
}
```

`fragments` 是本次整理范围内、发布时固化的原文副本，用于版本固定的原文查看。它不替代 `materials` 的原始文件；两者在首次构建时内容一致。

### 2.4 知识点页面

```json
{
  "id": "8e7f6971-...",
  "name": "进程",
  "version_id": "404bfe41-...",
  "html": "<p>进程是程序的一次执行……<a href=\"snippet:80696775-...\">原文</a></p>",
  "citations": [
    {"snippet_id": "80696775-...", "quote": "进程是程序的一次执行。",
     "filename": "教材节选（受控样本）.md", "start_line": 5, "end_line": 5,
     "chapter_title": "2.1 进程的定义"}
  ]
}
```

页面正文里的 `snippet:<id>` 链接是**程序生成的引用标记**，点击后应调用 2.5 的原文接口，而不是把 id 当外链打开。

### 2.5 原文片段

```json
{
  "id": "80696775-...", "version_id": "404bfe41-...",
  "filename": "教材节选（受控样本）.md", "chapter_title": "2.1 进程的定义",
  "start_line": 5, "end_line": 5,
  "markdown": "进程是程序的一次执行。进程是系统进行资源分配和调度的独立单位。",
  "html": "<p>进程是程序的一次执行。……</p>"
}
```

## 3. 图谱语义（03／07 必读）

- 节点只有两类：章节（`chapters`）和知识点（`concepts`），没有公式／例题节点。
- `contains`：`chapter → concept`，表示章节涵盖该知识点。`origin` 固定为 `source`，并带章节内的原文引用。它**不是**学习顺序。
- `precedes`：`concept → concept`，方向是“先学 from，再学 to”。`origin: source` 必须有引用；`origin: suggested` 是系统建议，可以没有引用。
- `contrasts`：`concept → concept`，用于辨析，**没有先后方向**。数据里保留 from／to 以便去重，但界面与路线不得把方向解释成学习顺序。
- 章节在原文中的排列顺序**不自动产生** `precedes`。只有模型明确抽取或推断的关系才会出现。
- 路线计算（07）只能使用 `precedes`；`contains` 用于组织，`contrasts` 不参与排序。

## 4. 引用与校验规则

- 模型只能引用本次输入提供的 `snippet_id`。程序校验：片段在范围内、`quote` 非空且在原文中（忽略空白差异）、章节归属必须有该章节内的引用。
- 关系端点必须存在；知识点不能以自身为端点；`source` 关系必须有引用。
- 每个知识点必须有且仅有一个页面；页面内 `snippet:` 引用必须先声明。
- 发布前会**重新执行快照完整性校验**，不信任快照里的 `validated` 标记。
- 引用合法只证明“能在原文定位”，**不证明结论在语义上被原文支持**。语义核对仍需人工样本验收（任务 14）。

## 5. 任务执行与故障语义

- 独立进程 `python -m campus.worker --data-dir <dir>` 轮询任务；应用启动时会自动拉起一个 worker。多个 worker 通过 SQLite 中的全局租约互斥，一次只跑一个整理任务。
- 六步固定为 `ingest → extract → integrate → render → validate → publish`。`ingest` 在创建任务时完成并保存原文范围；成功步骤的结果持久化，重试复用。
- 模型调用只对可重试错误（429／5xx／网络）最多重试 3 次；结构、引用、关系校验失败不重试，直接失败。
- 发布在数据库事务内完成，并带租约栅栏；同一任务重复发布是幂等的，不会产生第二个版本。
- 失败时任务置 `failed` 并保存 `error_code`／`error_message`；课程知识保持原状（首次失败就是没有可用知识）。
- 未预期异常会被捕获并记录为 `internal` 失败，worker 不退出。

## 6. 给成员 A（03／08／09／10）

- **03**：直接读 `GET /knowledge`（固定 `version_id`）即可获得章节、知识点、关系、原文引用。章节 `level`／`parent_id` 可用于目录，但不要据此生成前置关系。
- **08**：当前 `Knowledge.publish_task` 明确拒绝在已有已发布版本时发布。需要扩展为“以当前版本为 `parent_version_id` 的候选发布”，并在同一事务内比较指针，避免丢失更新。`knowledge_version.snapshot_json` 是自包含快照；若要拆表，先写迁移并验证旧版本仍可读。
- **09**：概念身份需要跨任务沿用。建议整合阶段输入上一版本的概念目录与 `id`，输出 `existing_id`／`new`；无法确认时按 Q34 保留独立身份并标记待核对，不要按同名强行合并。
- **10**：租约与步骤结果已经持久化。恢复入口是 `claim` 对 `running` 任务的重新领取；需要补的是明确的“中断”状态呈现与更细的重试策略。`retry` 只接受 `failed`。

## 7. 给成员 C（07）

- 输入：一个已发布快照的 `version_id`、目标知识点 `id`。
- 只用 `kind === "precedes"` 建图；`contains`／`contrasts` 不参与排序。
- 必须检测循环、缺口与 `origin: suggested` 的关系，并把不完整路线标为“部分可确定”，不能声称完整，也不能声称掌握度。
- 读取时固定 `version_id`，不要在一次路线计算中混读当前指针。

## 8. 给成员 B（04，下一步）

- 问答必须固定一个 `version_id`，并只在该快照的 `fragments`（或当前课程允许范围内的资料）中检索和引用。
- 回答引用沿用 `snippet_id + quote`，并在返回前复用同一套引用校验；校验失败的流式内容不能标记为完成。
- 选定知识点只是“提问焦点”，不能自动把范围缩成该知识点。

## 9. 已验证与限制

- 46 项 Python 测试、类型检查、构建、受控 Chromium 流程通过；包含租约接管竞态、包含关系完整性、页面失败后重试、跨段引用定义及旧响应防护。
- 真实 DeepSeek Flash `/responses` 以 high 思考和 JSON Schema 完成教材短样本的抽取、整合、页面生成；最终轮各阶段尝试数均为 1，发布 10 个知识点、21 条关系。
- 新进程读取已发布版本，10 个知识点页面及全部引用均通过浏览器核查；逐项对照原文定义和关系理由。过程、初次样本发现的问题及修复见[验收记录](verification-ticket-02-fixes.md)。
- 仅证明本次小样本可运行；不代表任意教材的语义正确性、所有 Schema 关键字或最大输出长度都已验证。大范围演示和约 20 题验收留给任务 14。
- 图谱入口为 `web/features/knowledge/KnowledgeWorkspace.tsx`，在 `web/app/App.tsx` 接入；专有样式限定在 `.knowledge-workspace`。

## 10. 复现受控浏览器验收

```powershell
# 生成受控数据（合成短文 + 脚本化模型，不是真实教材/模型）
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe .\scripts\seed_ticket02_fixture.py --data-dir .\data\browser-02

# 启动（另一个终端；检查脚本不会点击整理或调用模型）
.\.venv\Scripts\python.exe -m campus --data-dir .\data\browser-02 --port 8016

# 浏览器检查（第三个终端）
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe .\scripts\check_knowledge_browser.py --url http://127.0.0.1:8016 --screenshot .\data\browser-02.png
```

受控数据目录 `data/` 已被 `.gitignore` 排除，不会提交。

## 11. 当前限制清单

1. 仅首次构建；追加整理属于 08。
2. 单次范围 60,000 字符；超限拒绝，需拆分小节。
3. 知识点身份只在“同一任务重试 + 已发布版本内”稳定；跨版本沿用待 08／09。
4. 知识快照为 JSON，尚未拆成关系／证据／版本概念表；读取接口已按版本封装，迁移时需保留旧快照可读。
5. 引用校验是定位校验，不是语义正确性证明。
6. 任务 02 已完成真实短样本验收；任务 03 的章节概览与跨章节浏览仍需独立验收。
