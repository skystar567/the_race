# 任务 07：学习路线案例与实现

状态：**规则已实现于统一应用**（`campus/routes.py`、“路线”工作区）；下面的 8 个案例是验收目标，统一应用当前只自动化了其中链式、待核对和边界输入，**8 个案例尚未全部写成测试**，图谱路线高亮也未做。

## 规则

- 只用 `prerequisite` 排序；`contains`、`contrast` 不参与。
- 保留每条边的 `grounded/inferred` 与 `confirmed/unverified`。
- 循环、缺口、待核对显式呈现；只能展示可确定部分时状态为 `partial`/`blocked`。
- 当前学习位置只表示起点，不评分、不诊断掌握度。
- 同层按稳定知识点 ID 排序，结果确定。

## 案例

| 案例 | 输入 | 期望 |
| --- | --- | --- |
| R1 链式 | K1→K2→K3，目标 K3 | complete，[K1,K2,K3] |
| R2 分支 | K1→K2/K3，K2/K3→K4 | complete，K1 首 K4 尾，K2 在 K3 前（按 ID） |
| R3 循环 | K1→K2→K3→K1，目标 K3 | blocked，cycles=[K1,K2,K3]，不输出完整路线 |
| R4 缺口 | K9→K3→K4，K9 缺失 | partial，route=[K3,K4]，gaps 标 K9 |
| R5 混合 | contains + contrast + prerequisite | 只有 prerequisite 决定顺序，其余列入 excluded |
| R6 待核对 | K2→K3 unverified | partial，route 保留但 unverified 标出 |
| R7 当前起点 | K1→K2→K3→K4，current=K2 | route=[K3,K4]，prior=[K1,K2]，不称已掌握 |
| R8 循环+分支 | 环 K1/K2/K3，K5→K4→K3 | partial，可确定 [K5,K4]，同时报循环 |

统一应用输出字段：`version_id`、`target`、`current`、`status`、`route`、`prior`、`cycles`、`gaps`、`unverified`、`excluded_relations`、`warnings`；不返回单独的 `edges`。

## 当前仍未做

- 前端图谱高亮路线节点（当前只在“路线”列表展示）。
- 模型解释“为什么这样安排”（当前是确定性排序理由，没有额外 LLM 解释）。
- 真实死锁课程数据回归（当前真实演示只到 2.1.1）。
- 把 R1—R8 全部写成自动化测试（本目录只保留案例设计）。
