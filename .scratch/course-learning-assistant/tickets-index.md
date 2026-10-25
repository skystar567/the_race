# 校园课程学习助手开发任务索引

依据已确认的[父规格](spec.md)发布 15 个独立开发任务，按依赖顺序编号，分别归属四个里程碑。每个任务有自己的正文和验收条件，本页仅作导航。

发布时所有任务均为 `ready-for-agent`，85 项验收条件均未勾选；此状态表示规格充分，不代表前置任务已完成，也不表示已开始实现。执行前读取父规格、当前任务和前置任务；只有前置任务实际完成后，才进入相应任务。

当前进度（2026-10-25）：任务 01 的 6 项验收条件已完成。任务 02 勾选 6/7 项（真实模型、真实页面与图谱已验证；真实教材正文待补）；任务 04 勾选 6/7 项（真实模型问答、流式与引用已验证；真实教材代表问题待核对）；任务 05、06 各勾选 4/5 项、任务 11 勾选 4/5 项（代码与确定性测试完成；浏览器/真实模型验收及 08 的完整发布并发验收未执行）；任务 03、07—10、12—15 尚未实施。详情见[任务 01 验证记录](../../docs/verification-ticket-01.md)、[任务 02 验证记录](../../docs/verification-ticket-02.md)、[任务 02 交接](../../docs/handoff-ticket-02.md)、[任务 04 验证记录](../../docs/verification-ticket-04.md)、[任务 04 交接](../../docs/handoff-ticket-04.md)、[任务 05/06/11 验证记录](../../docs/verification-ticket-05-06-11.md)和[三人协作计划](../../docs/team-plan.md)。

## 任务与依赖

| 任务 | 里程碑 | 直接前置任务 |
| --- | --- | --- |
| [01 创建课程并导入可追溯的学习资料](issues/01-course-material-import.md) | M1 | 无 |
| [02 把一小节真实教材整理成知识图谱](issues/02-first-real-knowledge-graph.md) | M1 | [01](issues/01-course-material-import.md) |
| [03 按整理范围浏览章节与跨章节知识](issues/03-chapter-scope-navigation.md) | M1 | [02](issues/02-first-real-knowledge-graph.md) |
| [04 在明确课程范围内进行带依据问答](issues/04-grounded-course-questions.md) | M2 | [03](issues/03-chapter-scope-navigation.md) |
| [05 生成、编辑并保存个人笔记](issues/05-personal-study-notes.md) | M2 | [04](issues/04-grounded-course-questions.md) |
| [06 主动获取拓展解释并保留来源标记](issues/06-explicit-model-expansion.md) | M2 | [05](issues/05-personal-study-notes.md) |
| [07 围绕学习目标展示有依据的学习路线](issues/07-prerequisite-study-route.md) | M2 | [03](issues/03-chapter-scope-navigation.md) |
| [08 追加资料并一致发布新的课程知识](issues/08-incremental-knowledge-update.md) | M3 | [03](issues/03-chapter-scope-navigation.md) |
| [09 区分易混概念并展示资料冲突](issues/09-concept-identity-conflicts.md) | M3 | [08](issues/08-incremental-knowledge-update.md) |
| [10 在故障或重启后继续知识整理任务](issues/10-recover-knowledge-jobs.md) | M3 | [08](issues/08-incremental-knowledge-update.md) |
| [11 知识更新时保留问答依据与个人笔记](issues/11-preserve-learning-across-updates.md) | M3 | [05](issues/05-personal-study-notes.md)、[08](issues/08-incremental-knowledge-update.md) |
| [12 提交问题反馈并回查资料纠错](issues/12-evidence-based-corrections.md) | M3 | [09](issues/09-concept-identity-conflicts.md)、[11](issues/11-preserve-learning-across-updates.md) |
| [13 导出可独立阅读的课程资料包](issues/13-portable-course-export.md) | M4 | [06](issues/06-explicit-model-expansion.md)、[09](issues/09-concept-identity-conflicts.md)、[11](issues/11-preserve-learning-across-updates.md) |
| [14 构建真实演示课程并核查代表问题](issues/14-real-textbook-demo-course.md) | M4 | [04](issues/04-grounded-course-questions.md)、[09](issues/09-concept-identity-conflicts.md) |
| [15 一条命令启动并完成比赛演示](issues/15-local-demo-delivery.md) | M4 | [07](issues/07-prerequisite-study-route.md)、[10](issues/10-recover-knowledge-jobs.md)、[12](issues/12-evidence-based-corrections.md)、[13](issues/13-portable-course-export.md)、[14](issues/14-real-textbook-demo-course.md) |

依赖图的入口为 [01](issues/01-course-material-import.md)。编号给出建议实施顺序，依赖只表示实际阻塞；没有依赖关系的任务可在各自前置完成后独立推进。

所有任务沿用父规格中的技术栈、统一 deepseek-flash、模块职责、资料依据、版本发布和个人笔记约束。真实演示使用真实资料与模型流程；可控模型响应只用于重现验证场景。

## 与原开发清单的对应

原[开发任务清单](../../docs/implementation-plan.md)的 25 项工作全部纳入下列任务。此映射组织实施顺序，不更改原清单的完成状态，也不增加产品范围。

| 原清单项 | 对应任务 |
| --- | --- |
| M1.1 | [01](issues/01-course-material-import.md) |
| M1.2 | [01](issues/01-course-material-import.md) |
| M1.3 | [01](issues/01-course-material-import.md)、[03](issues/03-chapter-scope-navigation.md) |
| M1.4 | [02](issues/02-first-real-knowledge-graph.md) |
| M1.5 | [02](issues/02-first-real-knowledge-graph.md)、[04](issues/04-grounded-course-questions.md) |
| M1.6 | [02](issues/02-first-real-knowledge-graph.md)、[03](issues/03-chapter-scope-navigation.md) |
| M1.7 | [02](issues/02-first-real-knowledge-graph.md)、[03](issues/03-chapter-scope-navigation.md) |
| M2.1 | [04](issues/04-grounded-course-questions.md) |
| M2.2 | [04](issues/04-grounded-course-questions.md) |
| M2.3 | [06](issues/06-explicit-model-expansion.md) |
| M2.4 | [05](issues/05-personal-study-notes.md)、[06](issues/06-explicit-model-expansion.md) |
| M2.5 | [07](issues/07-prerequisite-study-route.md) |
| M2.6 | [03](issues/03-chapter-scope-navigation.md)、[04](issues/04-grounded-course-questions.md)、[05](issues/05-personal-study-notes.md)、[07](issues/07-prerequisite-study-route.md) |
| M3.1 | [08](issues/08-incremental-knowledge-update.md)、[09](issues/09-concept-identity-conflicts.md) |
| M3.2 | [09](issues/09-concept-identity-conflicts.md) |
| M3.3 | [08](issues/08-incremental-knowledge-update.md)、[11](issues/11-preserve-learning-across-updates.md) |
| M3.4 | [10](issues/10-recover-knowledge-jobs.md) |
| M3.5 | [12](issues/12-evidence-based-corrections.md) |
| M3.6 | [11](issues/11-preserve-learning-across-updates.md) |
| M4.1 | [13](issues/13-portable-course-export.md) |
| M4.2 | [14](issues/14-real-textbook-demo-course.md) |
| M4.3 | [14](issues/14-real-textbook-demo-course.md) |
| M4.4 | [10](issues/10-recover-knowledge-jobs.md)、[11](issues/11-preserve-learning-across-updates.md)、[15](issues/15-local-demo-delivery.md) |
| M4.5 | [15](issues/15-local-demo-delivery.md) |
| M4.6 | [15](issues/15-local-demo-delivery.md) |

## 用户故事覆盖

编号对应父规格中的 57 条用户故事；涉及多个功能的故事由相关任务共同验收。

| 任务 | 用户故事编号 |
| --- | --- |
| [01](issues/01-course-material-import.md) | 1、2、3、4、8、9、10、53 |
| [02](issues/02-first-real-knowledge-graph.md) | 7、11、12、14、15、17、46 |
| [03](issues/03-chapter-scope-navigation.md) | 5、6、11、12、13、16、17、41 |
| [04](issues/04-grounded-course-questions.md) | 18、19、20、21、22、23、24、25、26 |
| [05](issues/05-personal-study-notes.md) | 29、30、31、32、53 |
| [06](issues/06-explicit-model-expansion.md) | 27、28、33 |
| [07](issues/07-prerequisite-study-route.md) | 34、35、36、37 |
| [08](issues/08-incremental-knowledge-update.md) | 38、39、41、43、44、45 |
| [09](issues/09-concept-identity-conflicts.md) | 39、40、41、42、44 |
| [10](issues/10-recover-knowledge-jobs.md) | 7、45、46、47 |
| [11](issues/11-preserve-learning-across-updates.md) | 31、32、43、45、48 |
| [12](issues/12-evidence-based-corrections.md) | 49、50、31、48 |
| [13](issues/13-portable-course-export.md) | 33、51、52 |
| [14](issues/14-real-textbook-demo-course.md) | 55、56、57 |
| [15](issues/15-local-demo-delivery.md) | 3、53、54、55、56、57 |
