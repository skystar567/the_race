# 成员三（C）工作文件 · 合并版

本目录来自成员 C 在 `the_race-main` 中完成的 07、12、13、14、15 规划与实现记录，现已导入统一的 `the_race-ticket-03` 交付。原文件保留了当时的“被前置阻塞”视角；合并后接口已经可用，状态按下表更新。

**当前结论：07/12/13 的核心实现已进入统一应用；14 已在真实教材第 2 章至 2.1.1 节上跑完 20/20 问题并带引用；15 的运行手册与交付清单已按统一应用改写。** 原先的 24 题、两章（含死锁）演示仍只是计划，不能把 20/20 写成 24/24。

## 文件

| 文件 | 内容 | 在统一应用中的状态 |
| --- | --- | --- |
| [representative-questions.md](representative-questions.md) | 24 道真实教材题（20 核心 + 4 边界）与教材行号 | 问题表保留；当前真实运行是 20 题/2.1.1，见 `docs/evidence/demo-questions.json` |
| [questions.json](questions.json) | 24 题的结构化要点、来源、期望 | 计划；未在统一应用上跑 24 题 |
| [route-cases.md](route-cases.md) | 链、分支、循环、缺口、混合、待核对、当前起点、循环+分支 | 规则已实现于 `campus/routes.py` 与“路线”工作区 |
| [export-checklist.md](export-checklist.md) | 导出包结构、固定版本、历史引用、冲突/缺图 | 已实现于 `campus/exports.py`，真实 zip 已验证 |
| [feedback-cases.md](feedback-cases.md) | 反馈双状态、任务/解决分离、笔记保护 | 已实现于 `campus/learning_api.py`，真实回查已验证 |
| [demo-runbook.md](demo-runbook.md) | 启动、演示、异常案例、限制 | 已按统一应用改写 |

## 原成员 C 任务对照（合并后）

| 任务 | 统一应用中的落地 | 真实状态 |
| --- | --- | --- |
| 07 学习路线 | `campus/routes.py`、`RouteService`、`web/learning.tsx` 路线工作区；只用 `precedes`，保留循环/缺口/`suggested` | 路线接口真实返回 `partial`；8 个案例未全部写成自动化测试，图谱高亮未做 |
| 12 问题反馈 | 知识点/关系反馈、章节回查任务、候选发布、`changed/unchanged/failed` | 真实反馈 `1ffffbce...` → `resolved/unchanged`，任务与结论分开 |
| 13 导出资料包 | `campus/exports.py`，固定版本 zip，含知识页、关系、笔记、原文、materials、manifest、`conflicts.md` | 真实导出 HTTP 200，约 20 KB；未在资源管理器逐页手工打开 |
| 14 真实演示课程 | `scripts/demo_questions.py` + `docs/evidence/demo-questions.json` | **20/20 completed，20/20 带引用**；24 题和两章范围未跑 |
| 15 本机交付 | `docs/delivery-checklist.md`、`demo-runbook.md`、README 启动说明 | 本机可启动；`data/real02` 是真实更新历史，密钥已删除 |

## 接口依赖：已解除

原报告担心的 02→03、04/09、06/09/11、09/11 接口现在均已具备：

- 已发布版本的固定读取、概念 ID/别名、`contains/precedes/contrasts`、`source/suggested`、页面与原文引用：任务 02/03。
- 带引用的回答与资料不足、冲突记录：任务 04/09。
- 拓展标记、笔记引用与 health、历史版本：任务 05/06/11。
- 反馈回查任务与候选发布：任务 08/12。

因此 07/12/13 不再停留在案例层；仍缺的是“逐条 UI 细化”，不是接口阻塞。

## 仍需协商/补齐

1. **07**：图谱路线高亮、Flash 解释理由、真实死锁章节回归。
2. **12**：`unsupported` 与 `no-change` 细分、冲突未解决时保持 `open`、前端轮询 `running`。
3. **13**：导出期间强一致快照、在目标电脑手工解压打开、大教材体积/耗时。
4. **14**：24 题、两章（含 3.5—3.8）与缺图题的完整真实运行。
5. **15**：Python 版本说明统一（`pyproject.toml` 要求 3.11+；本机 3.11.10，README 旧文写 3.13）。

## 与统一应用的关系

- 统一应用的知识/版本/任务/问答/笔记/路线/导出/反馈实现在 `campus/` 与 `web/`，不是原 `the_race-main` 的 `campus/route.py`、`campus/feedback.py`、`campus/export.py`。
- 原始成员 C 代码保留在 `the_race-main`，本目录保留其验收思路、案例和问题表；不要按旧路径直接调用。
- 50 项统一测试、真实 20 问与限制见 [`docs/verification-tasks-04-13.md`](../verification-tasks-04-13.md) 和 [`docs/delivery-checklist.md`](../delivery-checklist.md)。
