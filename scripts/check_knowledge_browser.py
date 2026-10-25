"""Verify ticket 02 in a real browser against a controlled fixture.

Run after ``scripts/seed_ticket02_fixture.py`` and starting the app with the
same data directory. The fixture text and knowledge are test data, not a real
textbook run of DeepSeek.
"""

import argparse
import asyncio

from playwright.async_api import async_playwright, expect
from check_browser import delayed_response


async def check(args):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1480, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(args.url)

        nav = page.get_by_role("navigation", name="课程", exact=True)
        await nav.get_by_role("button").filter(has_text=args.course).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="全图", exact=True).click()

        await expect(page.locator(".graph-canvas canvas").first).to_be_visible()
        await expect(page.get_by_text("已发布", exact=True)).to_be_visible()
        await expect(page.locator(".concept-list")).to_contain_text("进程")
        await expect(page.locator(".concept-list")).to_contain_text("线程")

        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        await expect(page.locator(".concept-page")).to_contain_text("资源分配")
        await expect(page.locator(".concept-chapters")).to_contain_text("2.1 进程的定义")

        await page.locator(".concept-citations .citation").first.click()
        dialog = page.locator("dialog.source-dialog")
        await expect(dialog).to_be_visible()
        await expect(dialog).to_contain_text("原文依据")
        await expect(dialog).to_contain_text("进程是程序的一次执行")
        await expect(dialog).to_contain_text("教材节选（受控样本）.md")
        await page.get_by_role("button", name="关闭", exact=True).click()
        await expect(dialog).to_be_hidden()

        await page.locator(".concept-list").get_by_role("button", name="线程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("线程")
        await expect(page.locator(".concept-relations")).to_contain_text("前置")
        await expect(page.locator(".concept-relations")).to_contain_text("进程")
        await expect(page.locator(".concept-relations")).to_contain_text("系统推断")

        courses = await (await page.request.get(args.url + "/api/courses")).json()
        course_id = next(course["id"] for course in courses if course["name"] == args.course)
        snapshot = await (await page.request.get(args.url + f"/api/courses/{course_id}/knowledge")).json()
        process_id = next(concept["id"] for concept in snapshot["concepts"] if concept["name"] == "进程")
        pattern = args.url + f"/api/courses/{course_id}/knowledge/versions/*/concepts/{process_id}"
        async with delayed_response(page, pattern) as (arrived, deliver):
            await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
            await asyncio.wait_for(arrived.wait(), 10)
            await page.locator(".concept-list").get_by_role("button", name="线程", exact=True).click()
            await expect(page.locator(".concept-panel-head h2")).to_have_text("线程")
            await deliver()
            await page.wait_for_timeout(250)  # Allow the delivered response to render.
            await expect(page.locator(".concept-panel-head h2")).to_have_text("线程")

        process = next(concept for concept in snapshot["concepts"] if concept["id"] == process_id)
        pattern = args.url + f"/api/courses/{course_id}/knowledge/versions/*/sources/{process['citations'][0]['snippet_id']}"
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        async with delayed_response(page, pattern) as (arrived, deliver):
            await page.locator(".concept-citations .citation").first.click()
            await asyncio.wait_for(arrived.wait(), 10)
            await page.locator(".concept-list").get_by_role("button", name="线程", exact=True).click()
            await expect(page.locator(".concept-panel-head h2")).to_have_text("线程")
            await page.locator(".concept-citations .citation").first.click()
            await expect(dialog).to_contain_text("线程是进程中的一个执行单元")
            await deliver()
            await page.wait_for_timeout(250)
            await expect(dialog).to_contain_text("线程是进程中的一个执行单元")
            await dialog.get_by_role("button", name="关闭", exact=True).click()

        async def unavailable(route):
            await route.fulfill(status=503, content_type="application/json", body='{"detail":"暂时不可用，请重试"}')

        concept_pattern = args.url + f"/api/courses/{course_id}/knowledge/versions/*/concepts/{process_id}"
        await page.route(concept_pattern, unavailable, times=1)
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.get_by_role("alert")).to_contain_text("暂时不可用")
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        await page.route(pattern, unavailable, times=1)
        await page.locator(".concept-citations .citation").first.click()
        await expect(page.get_by_role("alert")).to_contain_text("暂时不可用")
        await page.locator(".concept-citations .citation").first.click()
        await expect(dialog).to_contain_text("进程是程序的一次执行")
        await dialog.get_by_role("button", name="关闭", exact=True).click()

        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)

        await page.reload()
        await expect(page.locator(".imported-badge")).to_have_text("已导入 · 已整理")
        # A newly imported file must not inherit another material's organized state.
        await page.get_by_label("选择 Markdown 文件").set_input_files({
            "name": "尚未整理的补充资料.md", "mimeType": "text/markdown",
            "buffer": "# 补充资料\n\n这份新资料尚未整理。\n".encode(),
        })
        await expect(page.locator(".document-heading h2")).to_have_text("尚未整理的补充资料")
        await expect(page.locator(".imported-badge")).to_have_text("已导入 · 尚未整理")
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="全图", exact=True).click()
        await expect(page.locator(".graph-canvas canvas").first).to_be_visible()
        await expect(page.locator(".concept-list")).to_contain_text("线程")

        await nav.get_by_role("button").filter(has_text=args.failed_course).click()
        await page.get_by_role("button", name="资料阅读", exact=True).click()
        await expect(page.locator(".imported-badge")).to_have_text("已导入 · 尚未整理")
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await expect(page.get_by_text("尚未整理成课程知识", exact=True)).to_be_visible()
        await expect(page.locator(".task-panel.failed")).to_contain_text("失败")
        await expect(page.locator(".task-panel.failed")).to_contain_text("模型输出被截断")
        status = await (await page.request.get(args.url + "/api/model/status")).json()
        if not status["configured"]:
            await expect(page.get_by_text("后端尚未配置 DEEPSEEK_API_KEY", exact=False)).to_be_visible()
            await expect(page.locator(".scope-actions .primary")).to_be_disabled()
        else:
            await expect(page.locator(".scope-actions .primary")).to_be_enabled()

        await page.set_viewport_size({"width": 390, "height": 844})
        await expect(page.locator(".task-panel.failed")).to_be_visible()
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page overflows"
        await nav.get_by_role("button").filter(has_text=args.course).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await expect(page.locator(".graph-canvas canvas").first).to_be_visible()
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile graph overflows"

        assert errors == [], errors
        await browser.close()
    print(
        "Browser flow passed: graph canvas, concept list, concept page, citation dialog, "
        "source text, relation direction/origin, reload persistence, failed task state, mobile."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="在受控任务 02 数据上执行浏览器验收。")
    parser.add_argument("--url", default="http://127.0.0.1:8016")
    parser.add_argument("--course", default="操作系统（受控验收样本）")
    parser.add_argument("--failed-course", default="整理失败（受控验收样本）")
    parser.add_argument("--screenshot")
    asyncio.run(check(parser.parse_args()))
