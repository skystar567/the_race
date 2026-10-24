# 校园课程学习助手

面向大学生个人学习的比赛 Demo 项目：将课程 Markdown 资料整理成可追溯的知识点页面与知识图谱，支持课程问答、个人笔记、学习路线和追加资料后的知识更新。

## 当前进度

产品方案和技术方案已确认，开发任务已拆分。当前仓库保存方案文档，尚未包含可运行的应用，任务清单中的功能均未实施。

比赛交付目标是可运行 Demo。第一版计划在本机运行，通过浏览器访问，支持一个使用者管理多门课程。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [产品方案](docs/product-plan.md) | 产品定位、功能边界、演示流程与验收标准 |
| [技术方案](docs/technical-design.md) | 技术栈、知识提取流程、模型接入、存储与版本设计 |
| [开发任务清单](docs/implementation-plan.md) | 四个开发里程碑、具体任务与完成标准 |
| [领域术语](CONTEXT.md) | 课程、知识点、关系、资料依据等概念的定义 |
| [产品讨论记录](docs/design-discussion.md) | 产品决策与教材检查记录 |

架构决策：

- [课程知识与个人笔记分开维护](docs/adr/0001-separate-course-knowledge-and-personal-notes.md)
- [以 SQLite 保存课程知识的权威状态](docs/adr/0002-sqlite-as-authoritative-knowledge-store.md)
- [由固定处理流程生成和发布知识](docs/adr/0003-controlled-knowledge-processing.md)
- [按知识版本发布并固定读取与引用](docs/adr/0004-publish-versioned-knowledge.md)

## 计划中的主要能力

- 导入 Markdown，选择课程资料的整理范围。
- 浏览章节与知识点图谱，查看包含、前置、对比关系及原文依据。
- 根据课程资料提问，主动选择模型拓展解释。
- 生成、编辑和保存个人笔记。
- 根据学习目标查看建议学习路线。
- 追加资料或反馈问题后更新知识，保留个人笔记和历史引用。
- 导出知识页面、关系索引、个人笔记及原始 Markdown。

## 已选技术

- 前端：React、TypeScript、Vite、Cytoscape.js。
- 后端：Python、FastAPI、本机后台工作进程。
- 存储：SQLite 与本地原始资料文件。
- 模型：DeepSeek API，统一使用 `deepseek-flash`。

具体配置、处理流程与验证安排以[技术方案](docs/technical-design.md)为准，运行效果待实现后验证。

## 演示材料

计划使用《计算机操作系统（第四版）》第 2 章及第 3 章的 3.5—3.8 节，展示真实预构建知识库与现场短资料增量。

方案中的教材路径用于记录开发环境中的材料位置；教材正文及图片未随本仓库发布。第一版只接收 Markdown，缺失图片会明确标注，不包含 PDF/OCR 输入与图片理解。
