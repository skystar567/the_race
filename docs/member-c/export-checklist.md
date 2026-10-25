# 任务 13：导出资料包与验收

状态：**已实现于统一应用 `campus/exports.py`**；真实导出已验证 HTTP 200 zip（约 20 KB），但尚未在目标电脑资源管理器里逐页手工打开。

## 包结构

```text
README.md
manifest.json          # 课程、版本、条目清单、每个文件 sha256
knowledge/index.md
knowledge/concepts/<concept-id>.md
relations.md
notes/index.md
notes/<note-id>.md
materials/README.md
materials/<material-id>.md
sources.md             # 片段锚点、资料、行号、引用原文
conflicts.md           # 有冲突时；同名不同义双方与出处
manifest.json
```

- 页面内相对链接由测试逐个解析，确保目标文件存在。
- 原始 Markdown 逐字节复制；`sources.md` 记录资料名与行号，不修改原始文件。
- 笔记保留正文、引用、模型拓展标记；导出固定调用时的版本与笔记快照。
- 缺失图片继续保留“未导入图片”标记，不生成假图片。

## 已覆盖的验收

- [x] 入口：`GET /api/courses/{id}/export`，前端“导出”下载 zip。
- [x] 四类内容：知识页面、关系索引、个人笔记、已导入原始 Markdown。
- [x] 固定知识版本：`manifest.knowledge_version`，页面/关系/来源来自同一版本。
- [x] 相对链接可用：`tests/test_learning.py` 解析知识页、笔记到 `sources.md` 的链接。
- [x] 原文保留：zip 内材料字节等于 `materials.raw()`。
- [x] 笔记、拓展标记、冲突双方出处、缺图标记保留。
- [x] 课程隔离：只读取当前 `course_id`。
- [x] manifest 记录文件哈希与计数。

## 仍需人工确认

- [ ] 在 Windows 资源管理器解压后，用浏览器/编辑器打开主流程。
- [ ] 旧笔记引用到非当前版本片段时，`sources.md` 是否收齐（当前实现按笔记引用收集）。
- [ ] 大教材（1.24 MB、4,923 片段）导出耗时与包体积（未测）。
- [ ] 中文文件名在 zip 解压后的显示。

## 限制

- 导出过程没有长事务锁；如果在导出期间发布新版本，`snapshot`/`notes.list` 分别在调用时读取，极端并发下可能不是同一瞬间（当前单用户、单 worker 风险低，但未做快照事务）。
- 不恢复缺图；不同步应用外修改。
