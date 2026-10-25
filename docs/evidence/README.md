# 任务 02 真实运行证据

本目录保存 2026-10-25 真实 `deepseek-flash` + 真实教材样本运行的证据；不包含 API Key。

| 文件 | 内容 |
| --- | --- |
| [`real02-sample.md`](real02-sample.md) | 从《计算机操作系统（第四版）》第 1046—1080 行逐行摘录的 4 KB 样本，原教材未修改 |
| [`real02-sample.source.json`](real02-sample.source.json) | 原教材摘要、样本摘要、起止行号 |
| [`real02-browser.png`](real02-browser.png) | Playwright + 本机 Chrome 对真实版本的图谱/知识点页面截图 |
| [`real02-all-tabs.png`](real02-all-tabs.png) | 问答、笔记、路线、反馈、导出五个新工作区的真实浏览器截图 |
| [`real02-chapter-filter.png`](real02-chapter-filter.png) | 真实版本按 2.1.1 章过滤后的图谱（25 → 18 个知识点） |
| [`demo-questions.json`](demo-questions.json) | 真实教材版本上的 20 个问题、状态、回答与引用（20/20 完成且带引用） |

运行结果：任务 `21213e77-9186-457a-980d-0def0d769706`，版本 `966721d0-0d91-46e1-b0c6-4c88cf8a9235`，12 个知识点、19 条关系、25 条引用；25/25 引用可映射回教材。详细记录见 [任务 02 验证](../verification-ticket-02.md)。

样本只是验证用的小节，不代表整本教材已整理；真实运行数据在 `data/real02/`（被 `.gitignore` 忽略）。
