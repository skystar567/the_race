# 成员三（C）工作文件包

这是从统一项目 `the_race-ticket-03` 单独取出的成员 C 工作文件，放在桌面便于查看、打包或交给队友。**它不是一份独立可运行的应用副本**；应用代码仍在 `the_race-ticket-03`，这里保留文档、24 题数据、20 题真实运行证据和演示脚本。

## 先看什么

1. [成员 C 合并版说明](docs/member-c/README.md) —— 07/12/13/14/15 的状态、接口解除情况、仍需补齐项。
2. [24 道代表问题](docs/member-c/representative-questions.md) 与 [结构化题库](docs/member-c/questions.json) —— 第 2 章 + 3.5—3.8 的计划，**尚未在统一应用上跑 24 题**。
3. [学习路线案例](docs/member-c/route-cases.md)、[导出验收清单](docs/member-c/export-checklist.md)、[反馈纠错案例](docs/member-c/feedback-cases.md)。
4. [本机演示运行手册](docs/member-c/demo-runbook.md) —— 统一应用的实际启动/演示命令。
5. [任务 04—14 真实验收](docs/verification-tasks-04-13.md) 与 [本机交付清单](docs/delivery-checklist.md)。

## 真实结果（不要混淆）

- 统一应用已在真实教材 **第 2 章至 2.1.1 节** 上完成 **20/20** 问题，全部带原文引用。
- 逐题记录：[`docs/evidence/demo-questions.json`](docs/evidence/demo-questions.json)
- 浏览器截图：[`docs/evidence/real02-all-tabs.png`](docs/evidence/real02-all-tabs.png)、[`docs/evidence/real02-chapter-filter.png`](docs/evidence/real02-chapter-filter.png)
- 成员 C 原计划的 **24 题、两章（含死锁 3.5—3.8）** 没有运行；不能把 20/20 写成 24/24。

## 文件结构

```text
成员三工作/
├─ README.md                         ← 本文件
├─ docs/
│  ├─ member-c/
│  │  ├─ README.md                   成员 C 合并版说明
│  │  ├─ representative-questions.md 24 题（计划）
│  │  ├─ questions.json              24 题结构化要点/行号
│  │  ├─ route-cases.md              路线 8 案例与契约
│  │  ├─ export-checklist.md         导出包结构与验收
│  │  ├─ feedback-cases.md           反馈双状态与纠错
│  │  └─ demo-runbook.md             本机演示运行手册
│  ├─ evidence/
│  │  ├─ demo-questions.json         20/20 真实问答证据
│  │  ├─ real02-all-tabs.png         五个工作区截图
│  │  └─ real02-chapter-filter.png   章节过滤截图
│  ├─ verification-tasks-04-13.md    03—14 实现与真实验收
│  └─ delivery-checklist.md          本机交付清单
└─ scripts/
   ├─ demo_acceptance.py             建课 + 首次整理 + 20 题的脚本
   └─ demo_questions.py              对已有版本跑 20 题
```

## 与统一代码的对应

| 能力 | 统一应用位置 |
| --- | --- |
| 学习路线 | `campus/routes.py`、`web/learning.tsx` 的“路线” |
| 导出 | `campus/exports.py`、`web/learning.tsx` 的“导出” |
| 反馈/回查 | `campus/learning_api.py`、`web/learning.tsx` 的“反馈” |
| 问答 | `campus/answers.py`、`campus/answer_store.py` |
| 笔记/历史 | `campus/notes_store.py`、`web/learning.tsx` 的“笔记” |
| 增量/冲突 | `campus/merge.py`、`campus/jobs.py`、`campus/knowledge.py` |

成员 C 的原始代码在其原工作目录（`campus/route.py`、`feedback.py`、`export.py` 等）中，**不要**按旧路径直接调用；统一应用已使用上面的新模块。

## 运行 20 题（需要完整应用与密钥）

```powershell
cd C:\Users\19549\Desktop\the_race-ticket-03
# 配置 .env 的 DEEPSEEK_API_KEY 后启动
.\.venv\Scripts\python.exe -m campus --data-dir data\real02 --port 8017

# 另一个终端
.\.venv\Scripts\python.exe scripts\demo_questions.py http://127.0.0.1:8017 99038ccf-8d9f-4f68-8123-1a4791e86d2a
```

## GitHub

已在 `ticket-03` 分支：

- <https://github.com/skystar567/the_race/tree/ticket-03/docs/member-c>
- 本次成员 C 文件提交：`2924f0961e94d8a22bbdafc554d601df1665d83c`

## 已知限制

- 24 题未跑；两章/死锁课程未整理。
- 07 的图谱路线高亮、Flash 解释理由未做。
- 12 的 `unsupported` 与 `unchanged` 未细分；前端未轮询 `checking`。
- 13 未在目标电脑资源管理器逐页打开；导出强一致快照未做。
- 本目录不含密钥、`data/`、`.env`、虚拟环境或 `node_modules`。
