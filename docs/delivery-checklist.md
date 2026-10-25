# 本机交付清单（任务 15）

## 1. 环境

- Windows 10/11，PowerShell 5.1 或 7。
- Python 3.11+（本机验证用 3.11.10）。
- Node.js 20+（本机验证用 24.16.0）与 npm。
- 本机 Chrome（浏览器验收使用 Playwright 调用本机 Chrome，不需要另外下载 Chromium）。
- 可访问 `https://api.deepseek.com` 的网络，真实整理/问答需要 `DEEPSEEK_API_KEY`。

## 2. 安装

```powershell
cd C:\Users\19549\Desktop\the_race-ticket-02-knowledge-graph-delivery
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm ci
npm run typecheck
npm run build
```

浏览器验收额外需要：

```powershell
.\.venv\Scripts\python.exe -m pip install playwright==1.62.0
```

## 3. 配置密钥

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

`.env` 已被 `.gitignore` 忽略；不要提交。没有密钥仍可浏览已发布知识、笔记、路线和导出，但不能新整理或问答。

## 4. 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
# 或
.\.venv\Scripts\python.exe -m campus --data-dir .\data\real02 --port 8017
```

打开 `http://127.0.0.1:8017`。演示数据在 `data/real02`（已忽略，不作为源码提交）。

若 PowerShell 限制脚本，使用 `-ExecutionPolicy Bypass`；直接运行 Python 不经过脚本签名检查。

## 5. 演示路径

1. 打开课程「操作系统真实验收 02」。
2. 「知识图谱」：25 个知识点、41 条关系；下方有 10 条冲突提示；可切换历史版本、按章节过滤；点知识点打开页面/原文。
3. 「问答」：提问“进程是什么？”，查看带 `[F:...]` 引用和原文弹窗；可打开“需要资料外拓展”。
4. 「笔记」：新建/编辑，查看引用；依据变化时显示检查提示。
5. 「路线」：目标选“前趋关系”，查看顺序与待核对关系。
6. 「反馈」：对知识点提交问题，点“重新核对”，查看 `changed/unchanged/failed`。
7. 「导出」：下载 zip，解压后从 `README.md` 进入知识、关系、笔记、原文。

## 6. 验收命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run typecheck
npm run build
```

真实 20 问（需要密钥和服务）：

```powershell
.\.venv\Scripts\python.exe scripts\demo_questions.py http://127.0.0.1:8017 99038ccf-8d9f-4f68-8123-1a4791e86d2a
```

预期：`20/20 completed, 20/20 cited`，输出 `docs/evidence/demo-questions.json`。

## 7. 数据与清理

- `data/` 保存 SQLite、上传原文、版本快照；备份时复制整个目录。
- `.env` 不随交付保存；验收结束后已删除。真实 key 曾在聊天中出现，建议到 DeepSeek 控制台重置。
- `data/real02` 是多次真实更新的历史（首版 12 个知识点，当前 25 个、10 条冲突）；不要把它当作手绘干净图谱。
- 演示用的 `docs/evidence/` 只含教材摘录和验证截图，不含密钥。

## 8. 当前限制

- 本机单用户，没有鉴权、多租户或账号隔离。
- 问答前端使用普通 JSON；SSE 后端已存在但界面未逐字显示。
- 路线列表不驱动图谱高亮；章节视图是过滤，不是折叠树。
- 同名冲突使用启发式，真实重复更新会保留较多同名条目。
- 原计划的两章（含死锁 3.5—3.8）演示未完成；真实演示只覆盖第 2 章至 2.1.1 节。
- 不支持 PDF/OCR、图片理解、图片恢复。
