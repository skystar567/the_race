# 任务 15：本机演示运行手册（合并版）

状态：**统一应用可在本机启动，真实教材版本已完成首次整理、两次增量/反馈更新和 20/20 带引用问答。** 本文是运行手册，不是“全部 24 题、两章范围已验收”的证明；24 题和死锁章节仍未跑。

## 一、环境

- Windows 10/11，PowerShell 5.1 或 7。
- Python 3.11+（本机 3.11.10；`pyproject.toml` 要求 3.11+，旧 README 的 3.13 说法已不再使用）。
- Node.js 24、npm 11；Chrome/Edge。
- DeepSeek：`deepseek-flash`，密钥只放后端 `.env` 或环境变量，不写前端、不进仓库。

## 二、首次准备与启动

```powershell
cd C:\Users\19549\Desktop\the_race-ticket-03
npm ci
npm run typecheck
npm run build

Copy-Item .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
# 或直接：
.\.venv\Scripts\python.exe -m campus --data-dir .\data\real02 --port 8017
```

访问 `http://127.0.0.1:8017`。`data/real02` 是真实教材验收留下的数据目录；没有密钥时仍可浏览已发布知识、笔记、路线和导出，但不能发起新整理/问答。

## 三、八步演示

| 步 | 操作 | 应看到 | 状态 |
| --- | --- | --- | --- |
| 1 | 打开课程“操作系统真实验收 02”，查看资料与章节 | 教材、章节、缺图提示 | 可用 |
| 2 | “知识图谱”：查看 25 个知识点、41 条关系、10 条冲突 | 图谱、冲突提示、当前/历史版本、章节过滤 | 可用 |
| 3 | 点“进程”知识点 | 真实页面、原文引用、来源弹窗 | 可用 |
| 4 | “问答”问“进程是什么？” | 带 `[F:...]` 引用的回答；不足时明确说明 | 需 key |
| 5 | 保存为笔记并编辑 | 笔记独立保存；依据变化提示 | 可用（生成回答需 key） |
| 6 | “路线”选“前趋关系” | 顺序、`partial`、待核对原因 | 可用 |
| 7 | “反馈”提交问题并“重新核对” | 任务状态、`changed/unchanged/failed` | 需 key |
| 8 | “导出”下载 zip | 知识、关系、笔记、原文、manifest、冲突记录 | 可用 |

真实 20 题记录：[`docs/evidence/demo-questions.json`](../evidence/demo-questions.json)（20/20 completed，20/20 带引用）。

## 四、异常短案例

1. **资料不足**：问“死锁和饥饿有什么区别？”当前 2.1.1 版本会说明资料不足，不能拿其他章节冒充。
2. **缺图**：问图 2-1/3-14 的图内细节；回答应说明图片未导入，不能编造结点。
3. **失败不发布**：断开 key/网络，任务失败；旧版本仍可读，界面显示失败原因。
4. **反馈未解决**：提交资料不支持的说法；任务完成但 `resolution=unchanged`，不能称已修正。
5. **重复任务**：一次只跑一个整理任务；已有 waiting/running 任务时新任务被拒绝。

## 五、真实 24 题（未运行）

原成员 C 的 24 题在 [`representative-questions.md`](representative-questions.md) 与 [`questions.json`](questions.json)，范围是第 2 章 + 3.5—3.8，需要更大的真实教材课程。当前 `scripts/demo_questions.py` 只跑 20 题/2.1.1；不要把它写成 24/24。

## 六、已知限制

- 本机单用户，无鉴权。
- 前端问答是普通 JSON，不是逐字流式；SSE 后端存在。
- 路线不驱动图谱高亮；章节视图是过滤，不是折叠树。
- 冲突识别是名称/定义/证据启发式；重复更新会保留较多同名条目。
- 原计划两章（含死锁 3.5—3.8）演示未完成。
- 不支持 PDF/OCR、图片理解、图片恢复。

## 七、交付前检查

- [x] `pytest` 50 项通过。
- [x] `npm run typecheck`、`npm run build` 通过。
- [x] 密钥已从 `.env` 删除；提交中没有密钥。
- [x] 真实 20 题有记录（非受控输出）。
- [ ] 24 题 / 两章范围真实运行。
- [ ] 在目标电脑资源管理器逐页打开导出包。
- [ ] 视觉回归/演示彩排。
