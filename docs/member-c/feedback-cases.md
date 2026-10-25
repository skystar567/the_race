# 任务 12：问题反馈与纠错（合并版）

状态：**已实现并完成一次真实验证**（`campus/learning_api.py`）。真实反馈 `1ffffbce-fdba-4011-8435-ada6d761f1bf` 指向“进程”，回查任务 `508457ac-1553-495a-9d61-7e1144523216` 完成后为 `resolved / unchanged`。尚无专门的自动化反馈测试。

## 双状态语义

| 状态 | 当前取值 | 含义 |
| --- | --- | --- |
| 任务状态 | `queued` / `running` / `completed` / `failed` | 整理任务是否执行完成 |
| 反馈状态 | `open` / `checking` / `resolved` | 反馈是否处理结束 |
| 反馈结论 | `changed` / `unchanged` / `failed` | 相关知识是否实际变化，或核对失败 |

任务 `completed` 不等于问题已修正：页面/定义没有变化时为 `unchanged`，任务失败时为 `failed`，都不能声称“已修正”。

## 已实现的流程

1. 从知识点或关系创建反馈（`POST /api/courses/{id}/feedback`）。
2. `POST /api/feedback/{id}/recheck` 找到目标的第一条原文引用，确定资料/章节范围。
3. 通过统一 `Jobs` 创建新的整理任务；成功时发布候选版本，旧版本保留。
4. 比较反馈前后的知识点定义/页面，给出 `changed` / `unchanged`；任务失败给出 `failed`。
5. 反馈不覆盖个人笔记；当前版本在失败时保持不变。

## 真实验证

- 反馈：`1ffffbce-fdba-4011-8435-ada6d761f1bf`
- 任务：`508457ac-1553-495a-9d61-7e1144523216`
- 结果：`resolved / unchanged`（任务完成但内容没有变化）
- 知识版本：`80d9128c-...`，父版本 `26510701-...`

## 仍需补

- 冲突仍未解决时保持 `open`（当前只比较页面/定义）。
- `unsupported` 与 `unchanged` 未细分。
- 前端在反馈处于 `checking` 时轮询任务状态；当前依赖服务端同步执行或再次点击。
- 专门的自动化测试，以及页面改变 → `changed` 的真实样例。
