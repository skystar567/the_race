# 校园课程学习助手

面向大学生个人学习的比赛 Demo 项目：将课程 Markdown 资料整理成可追溯的知识点页面与知识图谱，支持课程问答、个人笔记、学习路线和追加资料后的知识更新。

## 当前进度

任务 01 已实现并通过验收：本机课程创建与切换、Markdown 导入、章节目录、原文片段定位、公式与代码阅读、缺失图片提示，以及重启后的数据保留。已通过干净安装、10 项接口测试、类型检查、前端构建和真实浏览器检查，详情见[验证记录](docs/verification-ticket-01.md)。

知识图谱、模型整理、问答、笔记、路线和导出属于后续任务。当前资料状态为“已导入 · 尚未整理”，运行任务 01 不需要模型密钥。

比赛交付目标是可运行 Demo。第一版计划在本机运行，通过浏览器访问，支持一个使用者管理多门课程。

## 本机运行

开发环境使用 Python 3.13 和 Node.js 24。首次获取项目：

```sh
git clone https://github.com/skystar567/the_race.git
cd the_race
```

安装依赖并构建：

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm ci
npm run typecheck
npm run build
```

启动后访问 `http://127.0.0.1:8000`：

```sh
sh scripts/start.sh
```

服务仅监听本机。可通过 `--port 8001` 修改端口，通过 `--data-dir /你的/资料目录` 或 `CAMPUS_DATA_DIR` 环境变量指定持久数据目录，默认使用项目下的 `data/`。数据目录包含 SQLite 和导入原文，不要在保留学习资料时删除它。

前端开发可在后端运行时执行 `npm run dev`，开发服务器会把业务请求转发给本机 8000 端口。正式本机运行由后端提供前端构建产物。

## 共享教材与真实样本

仓库已包含[完整教材 Markdown](materials/textbooks/计算机操作系统（第四版）.md)及[第 2 章开头至 2.1.1 节的短样本](materials/samples/计算机操作系统（第四版）_第2章至2.1.1节.md)。成员拉取代码后即可在应用中导入；任务 02 建议从短样本开始，出处与使用说明见[共享开发教材](materials/README.md)。

也可以从仓库内的教材重新生成本机样本，原教材保持不变：

```sh
.venv/bin/python scripts/prepare_sample.py 'materials/textbooks/计算机操作系统（第四版）.md'
```

重新生成的本机样本位于 `data/samples/`。创建课程后，在界面中选择 `.md` 文件导入；旁边的 `.source.json` 记录原教材行号及文件摘要。界面中的行号对应实际上传文件，不把摘录后的行号冒充整本教材的行号。共享教材和样本位于 `materials/`，应用运行数据仍保存在不纳入版本管理的 `data/` 中。

## 验证

```sh
.venv/bin/python -m pytest
npm run typecheck
npm run build
```

接口测试通过应用公开接口检查课程隔离、重启持久化、原文保留、章节层级、引用定位、阅读内容和本机访问约束，不依赖模型服务。

真实浏览器检查需要允许启动 Chromium 和监听本机端口的环境。安装后，在单独数据目录启动应用，再从另一个终端运行检查：

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
sh scripts/start.sh --data-dir /tmp/campus-browser-check
# 另一个终端
.venv/bin/python scripts/check_browser.py
```

检查会创建两门测试课程，并验证导入、章节、公式、代码、缺图提示、原文、下载、课程隔离、刷新和窄屏布局。可传入 `--sample` 指定真实教材摘录，以及 `--screenshot` 保存截图。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [三人协作计划](docs/team-plan.md) | 三人任务分配、并行工作、依赖交接和交付约定 |
| [共享开发教材](materials/README.md) | 完整教材 Markdown、首次整理样本、出处与使用说明 |
| [任务 01 验证记录](docs/verification-ticket-01.md) | 实现范围、干净安装、浏览器验收和审查结果 |
| [开发规格](.scratch/course-learning-assistant/spec.md) | 本地任务追踪器中的完整规格、用户故事、实现与测试决定 |
| [独立开发任务](.scratch/course-learning-assistant/tickets-index.md) | 15 个完整功能任务的依赖、验收条件及原清单覆盖关系 |
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

完整教材 Markdown 和首次整理样本已放入 `materials/` 供成员共同开发，引用的图片文件未包含。方案中的原始教材路径保留为来源记录，成员使用仓库内的相对路径即可。第一版只接收 Markdown，缺失图片会明确标注，不包含 PDF/OCR 输入与图片理解。
