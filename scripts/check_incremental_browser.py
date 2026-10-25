"""Exercise append, atomic view switching and failure against the local fixture."""

import argparse
import asyncio

from playwright.async_api import async_playwright, expect

from check_browser import delayed_response


async def check(args):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1480, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(args.url)
        await page.get_by_role("navigation", name="课程", exact=True).get_by_role("button").filter(has_text="操作系统（受控验收样本）").click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="全图", exact=True).click()
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        await page.get_by_text("选择追加整理范围", exact=True).click()
        await page.get_by_role("checkbox", name="补充.md", exact=False).check()
        await page.get_by_role("button", name="追加整理", exact=True).click()
        await expect(page.locator(".update-reading")).to_contain_text("仍可阅读")
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        await page.locator(".concept-citations .citation").first.click()
        await expect(page.locator("dialog.source-dialog")).to_contain_text("进程是程序的一次执行")
        await page.locator("dialog.source-dialog").get_by_role("button", name="关闭", exact=True).click()
        # A response from the old version must not reopen its source dialog
        # after the graph and selected concept have switched to the new one.
        async with delayed_response(page, "**/knowledge/versions/*/sources/*") as (arrived, deliver):
            await page.locator(".concept-citations .citation").first.click()
            await asyncio.wait_for(arrived.wait(), 10)
            await expect(page.locator(".update-summary")).to_contain_text("新增 1", timeout=15000)
            await deliver()
            await expect(page.locator("dialog.source-dialog")).not_to_be_visible()
        await expect(page.locator(".update-summary")).to_contain_text("补充 1")
        await expect(page.locator(".concept-panel-head h2")).to_have_text("运行过程")
        await expect(page.locator(".concept-citations .citation")).to_have_count(2)
        await expect(page.get_by_role("checkbox", name="补充.md", exact=False)).to_be_disabled()

        await page.get_by_role("checkbox", name="含糊.md", exact=False).check()
        await page.get_by_role("button", name="追加整理", exact=True).click()
        await expect(page.locator(".update-summary")).to_contain_text("待核对 1", timeout=15000)
        await page.get_by_role("button", name="全图", exact=True).click()
        await page.locator(".concept-list").get_by_role("button", name="运行过程 · 待核对", exact=True).click()
        await expect(page.locator(".identity-review")).to_contain_text("尚不足以确认")
        await page.get_by_role("checkbox", name="无效.md", exact=False).check()
        await page.get_by_role("button", name="追加整理", exact=True).click()
        await expect(page.locator(".task-panel.failed")).to_be_visible(timeout=15000)
        await expect(page.locator(".task-panel.failed")).to_contain_text("原有知识")
        await expect(page.locator(".concept-panel-head h2")).to_have_text("运行过程")
        await expect(page.get_by_role("checkbox", name="未选.md", exact=False)).to_be_enabled()
        # Another window can import sources without changing the knowledge version.
        courses = await (await page.request.get(args.url + "/api/courses")).json()
        course = next(c for c in courses if c["name"] == "操作系统（受控验收样本）")
        response = await page.request.post(args.url + f"/api/courses/{course['id']}/materials?filename=later.md",
                                           data="# 新导入\n\n来自另一窗口，尚未整理。\n".encode())
        assert response.status == 201
        await page.get_by_role("button", name="刷新知识", exact=True).click()
        await expect(page.get_by_role("checkbox", name="later.md", exact=False)).to_be_enabled()
        await page.locator(".coverage-panel summary").click()
        await expect(page.locator(".coverage-material").filter(has_text="later.md")).to_contain_text("尚未整理")
        await page.locator(".coverage-panel summary").click()
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        await browser.close()
    print("Incremental browser passed: old reads, atomic update, retained selection, summary, uncertain identity, failure, scope, mobile.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8021")
    parser.add_argument("--screenshot")
    asyncio.run(check(parser.parse_args()))
