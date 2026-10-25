"""Study integration acceptance against serve_study_fixture.py (real HTTP/SQLite)."""

import argparse
import asyncio
import re
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, expect

from check_browser import delayed_response


@asynccontextmanager
async def delayed_create(page, url):
    arrived, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def handle(route):
        if route.request.method != "POST":
            await route.continue_()
            return
        response = await route.fetch()
        arrived.set()
        await release.wait()
        await route.fulfill(response=response)
        finished.set()

    async def deliver():
        release.set()
        await asyncio.wait_for(finished.wait(), 10)

    await page.route(url, handle)
    try:
        yield arrived, deliver
    finally:
        release.set()
        await page.unroute(url, handle)


async def publish(page, base, filename):
    materials = await (await page.request.get(base + "/materials")).json()
    material = next(m for m in materials if m["filename"] == filename)
    response = await page.request.post(base + "/tasks", data={"material_ids": [material["id"]], "chapter_ids": []})
    assert response.ok, await response.text()
    task = await response.json()
    for _ in range(100):
        tasks = await (await page.request.get(base + "/tasks")).json()
        status = next(t for t in tasks if t["id"] == task["id"])
        if status["status"] not in {"queued", "running"}:
            break
        await asyncio.sleep(0.1)
    assert status["status"] == "completed", status
    return status["version_id"]


async def check(args):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1480, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        courses = await (await page.request.get(args.url + "/api/courses")).json()
        course = next(c for c in courses if c["name"] == "操作系统（受控验收样本）")
        other = next(c for c in courses if c["id"] != course["id"])
        base = args.url + f"/api/courses/{course['id']}"
        snapshot = await (await page.request.get(base + "/knowledge")).json()
        version = snapshot["version_id"]
        await page.goto(args.url)
        navigation = page.get_by_role("navigation", name="课程", exact=True)
        await navigation.get_by_role("button").filter(has_text=course["name"]).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="全图", exact=True).click()
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.get_by_role("heading", name="进程", exact=True)).to_be_visible()
        await page.get_by_label("放大图谱", exact=True).click()
        zoom = await page.get_by_label("图谱缩放", exact=True).inner_text()
        await page.evaluate("window.studyGraph = document.querySelector('.graph-canvas canvas')")

        # Focus edits preserve a mixed scope and draft; an in-flight answer keeps its original focus.
        process_id = next(c["id"] for c in snapshot["concepts"] if c["name"] == "进程")
        await page.get_by_role("button", name="围绕此知识点提问", exact=True).click()
        focus_panel = page.get_by_role("complementary", name="课程问答", exact=True)

        async def select_mixed_scope():
            await focus_panel.get_by_role("button", name="调整", exact=True).click()
            await focus_panel.get_by_role("checkbox", name="教材节选（受控样本）.md", exact=True).check()
            await focus_panel.locator(".scope-group").filter(has_text="未整理页表.md").get_by_role("button", name="页表", exact=True).click()
            await focus_panel.get_by_role("button", name="调整", exact=True).click()
            await expect(focus_panel.locator(".qa-scope-row strong")).to_contain_text("1 份资料的全部原文")
            await expect(focus_panel.locator(".qa-scope-row strong")).to_contain_text("章节：页表")
            await expect(focus_panel.locator(".scope-selector")).to_have_count(0)

        await select_mixed_scope()
        await focus_panel.get_by_label("课程问题").fill("进程和线程有什么区别？")
        await focus_panel.get_by_label("清除提问焦点", exact=True).click()
        await expect(focus_panel.get_by_label("课程问题")).to_have_value("进程和线程有什么区别？")
        await expect(focus_panel.locator(".qa-scope-row strong")).to_have_text("1 份资料的全部原文；章节：页表")
        async with page.expect_request("**/answers/stream") as draft_request:
            await focus_panel.get_by_role("button", name="提问", exact=True).click()
        draft_payload = (await draft_request.value).post_data_json
        assert draft_payload["focus_concept_id"] is None
        assert len(draft_payload["material_ids"]) == len(draft_payload["chapter_ids"]) == 1
        await expect(focus_panel.locator(".qa-answer .badge.completed")).to_be_visible()
        await expect(focus_panel.locator(".answer-body")).to_contain_text("线程")
        await expect(focus_panel.locator(".qa-answer-scope")).to_contain_text("1 份资料的全部原文")
        await expect(focus_panel.locator(".qa-answer-scope")).to_contain_text("页表")
        await focus_panel.get_by_role("button", name="关闭课程问答").click()

        await page.get_by_role("button", name="围绕此知识点提问", exact=True).click()
        await select_mixed_scope()
        await focus_panel.get_by_label("课程问题").fill("进程发布中焦点清除验收")
        async with page.expect_request("**/answers/stream") as focused:
            await focus_panel.get_by_role("button", name="提问", exact=True).click()
        focused_payload = (await focused.value).post_data_json
        assert focused_payload["focus_concept_id"] == process_id
        await expect(focus_panel.locator(".answer-body.live")).to_contain_text("进程")
        await focus_panel.get_by_label("清除提问焦点", exact=True).click()
        await expect(focus_panel.get_by_label("课程问题")).to_have_value("进程发布中焦点清除验收")
        await expect(focus_panel.locator(".qa-scope-row strong")).to_have_text("1 份资料的全部原文；章节：页表")
        await expect(focus_panel.locator(".qa-answer-focus")).to_have_text("本次焦点：进程")
        await expect(focus_panel.locator(".focus-chip")).to_have_count(0)
        await expect(focus_panel.locator(".qa-answer .badge.completed")).to_be_visible(timeout=30000)
        records = await (await page.request.get(base + "/answers")).json()
        record = next(answer for answer in records if answer["question"] == "进程发布中焦点清除验收")
        assert record["status"] == "completed" and record["focus_concept_id"] == process_id
        assert record["scope"]["material_ids"] == focused_payload["material_ids"]
        assert record["scope"]["chapter_ids"] == focused_payload["chapter_ids"]
        assert "1 份资料的全部原文" in record["scope"]["label"] and "页表" in record["scope"]["label"]
        await focus_panel.get_by_label("课程问题").fill("进程清除焦点后续提问")
        async with page.expect_request("**/answers/stream") as unfocused:
            await focus_panel.get_by_role("button", name="提问", exact=True).click()
        next_payload = (await unfocused.value).post_data_json
        assert next_payload["focus_concept_id"] is None
        assert next_payload["material_ids"] == focused_payload["material_ids"]
        assert next_payload["chapter_ids"] == focused_payload["chapter_ids"]
        await expect(focus_panel.locator(".qa-answer .badge.completed")).to_be_visible()
        await expect(focus_panel.locator(".qa-answer-focus")).to_have_text("本次焦点：未设置")
        await focus_panel.get_by_role("button", name="关闭课程问答").click()

        # Default and explicit scopes include imported but unorganized material.
        await page.get_by_role("button", name="课程提问", exact=True).click()
        qa = page.get_by_role("complementary", name="课程问答", exact=True)
        await expect(qa).to_contain_text("全部已导入资料")
        await qa.get_by_label("课程问题", exact=True).fill("页表记录什么？")
        async with page.expect_request("**/answers/stream") as started:
            await qa.get_by_role("button", name="提问", exact=True).click()
        assert (await started.value).post_data_json["version_id"] == version
        await expect(qa.locator(".qa-answer .badge.completed")).to_be_visible()
        await expect(qa.locator(".answer-body")).to_contain_text("虚拟页到物理页框")
        await qa.locator(".answer-citations button").first.click()
        await expect(page.get_by_role("dialog", name="原文依据")).to_contain_text("未整理页表.md")
        await expect(page.get_by_role("dialog", name="原文依据")).to_contain_text("虚拟页到物理页框")
        await page.get_by_role("dialog", name="原文依据").get_by_role("button", name="关闭", exact=True).click()
        await qa.get_by_role("button", name="调整", exact=True).click()
        await qa.get_by_role("checkbox", name="未整理页表.md", exact=True).check()
        await qa.get_by_label("课程问题").fill("页表如何映射？")
        async with page.expect_request("**/answers/stream") as scoped:
            await qa.get_by_role("button", name="提问", exact=True).click()
        assert len((await scoped.value).post_data_json["material_ids"]) == 1
        await expect(qa.locator(".qa-answer .badge.completed")).to_be_visible()
        group = qa.locator(".scope-group").filter(has_text="未整理页表.md")
        await group.get_by_role("checkbox").uncheck()
        await group.get_by_role("button", name="页表", exact=True).click()
        await qa.get_by_label("课程问题").fill("页表章节解释")
        async with page.expect_request("**/answers/stream") as chapter:
            await qa.get_by_role("button", name="提问", exact=True).click()
        scope = (await chapter.value).post_data_json
        assert len(scope["chapter_ids"]) == 1 and scope["material_ids"] == []
        await expect(qa.locator(".qa-answer .badge.completed")).to_be_visible()
        await qa.get_by_role("button", name="保存为个人笔记", exact=True).click()
        editor = page.get_by_role("region", name="笔记编辑器", exact=True)
        await expect(editor).to_be_visible()
        await expect(editor.locator(".note-citations .citation").first).to_be_visible()
        await editor.locator(".note-citations .citation").filter(has_text="页表记录").click()
        await expect(page.get_by_role("dialog", name="原文依据")).to_contain_text("页表记录")
        await page.get_by_role("dialog", name="原文依据").get_by_role("button", name="关闭", exact=True).click()
        notes = await (await page.request.get(base + "/notes")).json()
        answer_note = notes[0]
        note_url = base + "/notes/" + answer_note["id"]

        # Actual persisted save response is delayed while the user types a new draft.
        await editor.get_by_role("button", name="编辑", exact=True).click()
        body = editor.get_by_label("笔记正文", exact=True)
        await body.fill("已提交的第一份草稿。")
        async with delayed_response(page, note_url) as (arrived, deliver):
            await editor.get_by_role("button", name="保存修改", exact=True).click()
            await asyncio.wait_for(arrived.wait(), 10)
            await body.fill("保存期间继续输入，必须保留。")
            await publish(page, base, "身份与冲突.md")
            await deliver()
        await expect(body).to_have_value("保存期间继续输入，必须保留。")
        await expect(editor.get_by_role("button", name="保存修改", exact=True)).to_be_enabled()
        await editor.get_by_role("button", name="保存修改", exact=True).click()
        await expect(editor.get_by_role("button", name="已保存", exact=True)).to_be_visible()
        saved = await (await page.request.get(note_url)).json()
        assert saved["body_md"] == "保存期间继续输入，必须保留。" and saved["revision"] == 3

        # A second client makes the editor stale. A 409 retains the local draft.
        await body.fill("409 后仍须保留的草稿。")
        response = await page.request.put(note_url, data={"title": saved["title"], "body_md": "另一个窗口的服务器修订。", "revision": saved["revision"]})
        assert response.ok
        await editor.get_by_role("button", name="保存修改", exact=True).click()
        await expect(page.get_by_role("button", name="重新读取服务器版本")).to_be_visible()
        await expect(body).to_have_value("409 后仍须保留的草稿。")
        page.once("dialog", lambda dialog: dialog.dismiss())
        await page.get_by_role("button", name="新建手写笔记").click()
        await expect(body).to_have_value("409 后仍须保留的草稿。")
        page.once("dialog", lambda dialog: dialog.dismiss())
        await navigation.get_by_role("button").filter(has_text=other["name"]).click()
        await expect(body).to_have_value("409 后仍须保留的草稿。")
        page.once("dialog", lambda dialog: dialog.accept())
        await page.get_by_role("button", name="重新读取服务器版本").click()
        await expect(editor.locator(".note-preview")).to_contain_text("另一个窗口的服务器修订。")

        # Same-version graph and concept detail survive note navigation.
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        assert await page.evaluate("window.studyGraph === document.querySelector('.graph-canvas canvas')")
        assert await page.get_by_label("图谱缩放", exact=True).inner_text() == zoom
        await qa.get_by_role("button", name="关闭课程问答").click()
        await expect(page.get_by_role("heading", name="进程", exact=True)).to_be_visible()

        # Publish externally while this tab intentionally remains on the previous version.
        async with page.expect_request("**/notes/generate") as generated:
            await page.get_by_role("button", name="生成个人笔记", exact=True).click()
        assert (await generated.value).post_data_json["version_id"] == version
        await expect(editor).to_contain_text("依据版本 " + version[:8])
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        async with page.expect_request("**/expansions") as expanded:
            await page.get_by_role("button", name="获取资料外拓展解释", exact=True).click()
        assert (await expanded.value).post_data_json["version_id"] == version
        expansion = page.locator(".concept-panel-holder .expansion-box")
        await expect(expansion).to_contain_text("超出课程资料，不是教材事实")
        await expansion.get_by_role("button", name="保存为个人笔记", exact=True).click()
        await expect(editor).to_contain_text("模型补充（超出课程资料）")
        await editor.get_by_role("button", name="编辑", exact=True).click()
        await editor.get_by_label("笔记正文").fill("学生自行编辑的拓展理解。")
        await editor.get_by_role("button", name="保存修改", exact=True).click()
        await expect(editor.get_by_label("笔记正文")).to_have_value(re.compile("模型补充（超出课程资料）"))

        # Refresh and inspect a historical answer; its frozen source remains available.
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="刷新知识", exact=True).click()
        await expect(page.locator(".graph-toolbar")).not_to_contain_text(version[:8])
        await page.get_by_role("button", name="课程提问", exact=True).click()
        await qa.locator(".qa-history-item").filter(has_text="页表如何映射？").click()
        await expect(qa.locator(".qa-answer-head")).to_contain_text(version[:8])
        await qa.locator(".answer-citations button").first.click()
        await expect(page.get_by_role("dialog", name="原文依据")).to_contain_text("页表记录")
        await page.get_by_role("dialog", name="原文依据").get_by_role("button", name="关闭", exact=True).click()
        # While streaming, a second real publication must not mix versions.
        visible_version = (await (await page.request.get(base + "/knowledge")).json())["version_id"]
        await qa.get_by_label("课程问题").fill("进程发布中验收")
        await qa.get_by_role("button", name="提问", exact=True).click()
        await expect(qa.locator(".answer-body.live")).to_contain_text("进程")
        next_version = await publish(page, base, "增量复习.md")
        assert next_version != visible_version
        await expect(page.locator(".graph-toolbar")).to_contain_text(visible_version[:8])
        await expect(qa.locator(".qa-answer .badge.completed")).to_be_visible(timeout=30000)
        await expect(qa.locator(".qa-answer-head")).to_contain_text(visible_version[:8])
        await qa.locator(".answer-citations button").first.click()
        await expect(page.get_by_role("dialog", name="原文依据")).to_contain_text(visible_version[:8])
        await page.get_by_role("dialog", name="原文依据").get_by_role("button", name="关闭", exact=True).click()
        await qa.get_by_label("课程问题").fill("进程中断验收")
        await qa.get_by_role("button", name="提问", exact=True).click()
        await expect(qa.locator(".qa-answer .badge.interrupted")).to_be_visible()
        await expect(qa).to_contain_text("受控连接中断")
        await expect(qa.get_by_role("button", name="保存为个人笔记", exact=True)).to_have_count(0)

        await qa.get_by_label("课程问题").fill("进程发布中主动停止")
        await qa.get_by_role("button", name="提问", exact=True).click()
        await expect(qa.locator(".answer-body.live")).to_contain_text("进程")
        await qa.get_by_role("button", name="停止", exact=True).click()
        await expect(qa.locator(".qa-answer .badge.interrupted")).to_be_visible()
        await expect(qa.get_by_label("课程问题")).to_be_enabled()

        # Late responses from a different course must not replace the current list.
        await page.get_by_role("button", name="个人笔记", exact=True).click()
        await navigation.get_by_role("button").filter(has_text=other["name"]).click()
        await expect(page.get_by_text("还没有笔记。", exact=True)).to_be_visible()
        async with delayed_response(page, base + "/notes") as (arrived, deliver):
            await navigation.get_by_role("button").filter(has_text=course["name"]).click()
            await asyncio.wait_for(arrived.wait(), 10)
            await navigation.get_by_role("button").filter(has_text=other["name"]).click()
            await deliver()
        await expect(page.get_by_text("还没有笔记。", exact=True)).to_be_visible()
        await expect(page.locator(".note-item")).to_have_count(0)
        await navigation.get_by_role("button").filter(has_text=course["name"]).click()
        await expect(page.locator(".note-item")).to_have_count(3)
        items = await (await page.request.get(base + "/notes")).json()
        async with delayed_response(page, base + "/notes/" + items[1]["id"]) as (arrived, deliver):
            await page.locator(".note-item").nth(1).click()
            await asyncio.wait_for(arrived.wait(), 10)
            await page.get_by_role("button", name="资料阅读", exact=True).click()
            async with page.expect_response(base + "/notes"):
                await page.get_by_role("button", name="个人笔记", exact=True).click()
            await expect(editor).to_have_count(0)
            await expect(page.get_by_text("正在读取个人笔记…", exact=True)).to_be_visible()
            await deliver()
        await expect(editor.get_by_label("笔记标题")).to_have_value(items[1]["title"])
        await expect(editor.get_by_role("button", name="编辑", exact=True)).to_be_visible()
        await editor.get_by_role("button", name="编辑", exact=True).click()
        await editor.get_by_label("笔记正文").fill("切换笔记前的未保存草稿。")
        page.once("dialog", lambda dialog: dialog.dismiss())
        await page.locator(".note-item").nth(0).click()
        await expect(editor.get_by_label("笔记正文")).to_have_value("切换笔记前的未保存草稿。")
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="个人笔记", exact=True).click()
        await expect(editor.get_by_label("笔记正文")).to_have_value("切换笔记前的未保存草稿。")
        async with delayed_create(page, base + "/notes") as (arrived, deliver):
            page.once("dialog", lambda dialog: dialog.accept())
            await page.get_by_role("button", name="新建手写笔记").click()
            await asyncio.wait_for(arrived.wait(), 10)
            await page.get_by_role("button", name="资料阅读", exact=True).click()
            async with page.expect_response(base + "/notes"):
                await page.get_by_role("button", name="个人笔记", exact=True).click()
            await expect(editor).to_have_count(0)
            await expect(page.get_by_text("正在读取个人笔记…", exact=True)).to_be_visible()
            await deliver()
        await expect(editor.get_by_label("笔记标题")).to_have_value("未命名笔记")
        await editor.get_by_label("笔记标题").fill("手写复习笔记")
        await editor.get_by_label("笔记正文").fill("手写理解不会写回课程知识。")
        await editor.get_by_role("button", name="保存修改", exact=True).click()
        await expect(editor.get_by_role("button", name="已保存", exact=True)).to_be_visible()
        await expect(page.locator(".note-item")).to_have_count(4)
        await expect(editor.get_by_label("笔记标题")).to_have_value("手写复习笔记")
        await page.set_viewport_size({"width": 390, "height": 844})
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        assert not errors, errors
        await browser.close()
        print("Study browser acceptance passed: scopes/sources, notes, delayed saves, 409 drafts, explicit expansions, pinned versions, graph persistence, stream failures, course isolation, mobile.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8036")
    parser.add_argument("--screenshot")
    asyncio.run(check(parser.parse_args()))
