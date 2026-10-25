# 校园课程学习助手

面向大学生个人学习的比赛 Demo 项目：将课程 Markdown 资料整理成可追溯的知识点页面与知识图谱，支持课程问答、个人笔记、学习路线和追加资料后的知识更新。

## 当前进度

任务 01 已实现并通过验收：本机课程创建与切换、Markdown 导入、章节目录、原文片段定位、公式与代码阅读、缺失图片提示，以及重启后的数据保留。已通过干净安装、10 项接口测试、类型检查、前端构建和真实浏览器检查，详情见[验证记录](docs/verification-ticket-01.md)。

任务 02 已通过小样本验收：真实 DeepSeek Flash 整理教材短样本，生成 10 个知识点、21 条关系；46 项 Python 测试、类型检查、构建、受控及真实知识浏览器流程通过。任务接管、包含关系校验、失败重试和旧响应覆盖问题已修复。详情见[修复与真实验收记录](docs/verification-ticket-02-fixes.md)及[接口交接](docs/handoff-ticket-02.md)。

任务 03 已实现多章节范围状态、默认章节概览、跨章节关联与全图、返回图谱时的位置保留。真实双片段验收生成 4 个知识点、8 条关系，两个概念跨章节共用身份；48 项测试及浏览器流程通过。见[验证记录](docs/verification-ticket-03.md)和[接口交接](docs/handoff-ticket-03.md)。

任务 08 已完成追加资料、稳定身份、候选校验及一致发布；真实小样本新增 2 个、补充 2 个知识点，60 项测试通过。见[验证记录](docs/verification-ticket-08.md)和[接口交接](docs/handoff-ticket-08.md)。

问答、笔记、路线、冲突处理和导出仍属后续任务。未配置模型凭据时，资料阅读与已发布知识浏览可用，但不能发起真实整理。

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

Windows PowerShell 使用 `.\.venv\Scripts\python.exe` 安装依赖，构建命令相同。

模型整理需要后端凭据。复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`；`.env`、环境文件备份、`*.pem`、`*.key` 和 `secrets/` 均被忽略；`.env.example` 仅保留空密钥模板。密钥只留在后端进程，不要提交，也不要放进前端。

启动后访问 `http://127.0.0.1:8000`：

```sh
sh scripts/start.sh
```

```powershell
.\scripts\start.ps1
```

服务仅监听本机。可通过 `--port 8001` 修改端口，通过 `--data-dir /你的/资料目录` 或 `CAMPUS_DATA_DIR` 环境变量指定持久数据目录，默认使用项目下的 `data/`。数据目录包含 SQLite 和导入原文，不要在保留学习资料时删除它。

应用启动时会同时拉起一个后台整理进程；任务进度因此不依赖浏览器是否保持打开。

前端开发可在后端运行时执行 `npm run dev`，开发服务器会把业务请求转发给本机 8000 端口。正式本机运行由后端提供前端构建产物。

## 共享教材与真实样本

仓库已包含[完整教材 Markdown](materials/textbooks/计算机操作系统（第四版）.md)及[第 2 章开头至 2.1.1 节的短样本](materials/samples/计算机操作系统（第四版）_第2章至2.1.1节.md)。成员拉取代码后即可在应用中导入；任务 02 建议从短样本开始，出处与使用说明见[共享开发教材](materials/README.md)。

也可以从仓库内的教材重新生成本机样本，原教材保持不变：

```sh
.venv/bin/python scripts/prepare_sample.py 'materials/textbooks/计算机操作系统（第四版）.md'
```

重新生成的本机样本位于 `data/samples/`。创建课程后，在界面中选择 `.md` 文件导入；旁边的 `.source.json` 记录原教材行号及文件摘要。界面中的行号对应实际上传文件，不把摘录后的行号冒充整本教材的行号。共享教材和样本位于 `materials/`，应用运行数据仍保存在不纳入版本管理的 `data/` 中。

## 知识整理

1. 在「资料阅读」中导入 Markdown，再切到「知识图谱」。
2. 选择整份资料或具体章节作为整理范围；单次上限 60,000 字符，超出会明确拒绝而不是截断。
3. 点击「开始整理」后，任务按 `读取原文 → 抽取知识点 → 整合 → 生成页面 → 校验 → 发布` 六步执行；界面显示每一步状态，失败显示原因并可重试。成功步骤会复用。
4. 校验失败、空输出、截断或无效引用都不会发布；首次失败时界面明确显示“尚未整理”，不会出现空壳知识库。
5. 发布后默认显示章节概览，点击章节展开知识点；可切换跨章节关联和全图。知识点与原文引用绑定同一版本，关闭详情后保留图谱位置。资料阅读和图谱范围面板区分未整理、部分已整理与已整理，范围外内容不会被算作已完成。
6. 再导入新资料后，打开「选择追加整理范围」并点击「追加整理」。只处理尚未整理片段；旧知识可继续阅读，通过校验后统一切换，并显示新增、补充及待核对数量。失败保留旧知识。身份不确定的同名概念独立保留，不自动合并。
7. 「刷新知识」同步知识与整理范围。失败任务只有在基准版本未变且同课程没有其他活动任务时才能重试；版本已变化时重新发起整理。

## 验证

```sh
.venv/bin/python -m pytest
npm run typecheck
npm run build
```

Python 测试通过应用公开接口与受控模型 transport 检查课程隔离、重启持久化、原文保留、章节层级、引用定位、首次发布、版本固定读取、失败不发布、重试复用、租约互斥与重复发布。另覆盖增量稳定身份、连续追加、无效候选、旧版保留与过期发布。共 60 项，不访问外部模型。

真实浏览器检查需要允许启动 Chromium 和监听本机端口的环境。安装后，在单独数据目录启动应用，再从另一个终端运行检查：

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
sh scripts/start.sh --data-dir /tmp/campus-browser-check
# 另一个终端
.venv/bin/python scripts/check_browser.py
```

检查会创建两门测试课程，并验证导入、章节、公式、代码、缺图提示、原文、下载、课程隔离、刷新和窄屏布局。可传入 `--sample` 指定真实教材摘录，以及 `--screenshot` 保存截图。

任务 02 的图谱流程使用受控数据单独检查（合成短文 + 脚本化模型，不是真实教材或真实模型输出）：

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe .\scripts\seed_ticket02_fixture.py --data-dir .\data\browser-02
.\.venv\Scripts\python.exe -m campus --data-dir .\data\browser-02 --port 8016
# 另一个终端
.\.venv\Scripts\python.exe .\scripts\check_knowledge_browser.py --url http://127.0.0.1:8016
```

任务 03 复用上述受控夹具，另运行 `scripts/check_chapter_browser.py --url http://127.0.0.1:8016` 检查多视图与位置保留。真实知识的只读检查方式见任务 03 验证记录，不会重复消耗模型额度。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [三人协作计划](docs/team-plan.md) | 三人任务分配、并行工作、依赖交接和交付约定 |
| [前端与资料接口交接](docs/frontend-handoff.md) | A 已完成的前端拆分、B/C 接入位置、现有接口与待交接知识接口 |
| [共享开发教材](materials/README.md) | 完整教材 Markdown、首次整理样本、出处与使用说明 |
| [任务 01 验证记录](docs/verification-ticket-01.md) | 实现范围、干净安装、浏览器验收和审查结果 |
| [任务 02 验证记录](docs/verification-ticket-02.md) | 知识整理实现、确定性测试、浏览器验收、未验证项与验收勾选说明 |
| [任务 03 验证与交接](docs/verification-ticket-03.md) | 多章节真实样本、图谱回归、范围 API 与后续接入 |
| [任务 08 验证与交接](docs/verification-ticket-08.md) | 小样本增量、稳定身份、失败保留、迁移和版本接口 |
| [任务 02 交接](docs/handoff-ticket-02.md) | 版本、任务、图谱与引用契约，供 03／04／07 及 08 使用 |
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

具体配置、处理流程与验证安排以[技术方案](docs/technical-design.md)为准；后续能力按任务逐项验收。

## 演示材料

计划使用《计算机操作系统（第四版）》第 2 章及第 3 章的 3.5—3.8 节，展示真实预构建知识库与现场短资料增量。

完整教材 Markdown 和首次整理样本已放入 `materials/` 供成员共同开发，引用的图片文件未包含。方案中的原始教材路径保留为来源记录，成员使用仓库内的相对路径即可。第一版只接收 Markdown，缺失图片会明确标注，不包含 PDF/OCR 输入与图片理解。
