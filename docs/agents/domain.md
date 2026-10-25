# Domain Docs

## Layout

采用 single-context：根目录 `CONTEXT.md` 保存领域术语，`docs/adr/` 保存架构决策。
沿用现有文档。

## Before exploring

- 探索项目之前，阅读根目录 `CONTEXT.md`。
- 阅读 `docs/adr/` 中与当前工作相关的决策。
- 如果以后出现 `CONTEXT-MAP.md`，按其指向读取相关领域的术语和 ADR。
- 文档缺失时直接继续，不为缺失本身要求补建；domain-modeling 在术语或决策明确后按需创建。

## Vocabulary and decisions

- 在规格、任务、方案和测试中使用领域术语表中的名称及定义。
- 遇到术语缺口，先检查是否已有对应概念；确有缺口时交由 domain-modeling 补充。
- 若拟议变更与现有 ADR 冲突，明确指出相关决策及重新讨论的理由。
