"""Check semantic identities, conflict sources and retry using a running fixture."""

import argparse
import asyncio

from playwright.async_api import async_playwright, expect


async def check(args):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1480, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        courses = await (await page.request.get(args.url + "/api/courses")).json()
        course = next(c for c in courses if c["name"] == "操作系统（受控验收样本）")
        base = args.url + f"/api/courses/{course['id']}"
        before = await (await page.request.get(base + "/knowledge")).json()
        old_process = next(c for c in before["concepts"] if c["name"] == "进程")
        old_thread = next(c for c in before["concepts"] if c["name"] == "线程")
        await page.goto(args.url)
        navigation = page.get_by_role("navigation", name="课程", exact=True)
        await navigation.get_by_role("button").filter(has_text=course["name"]).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_text("选择追加整理范围", exact=True).click()
        await page.get_by_role("checkbox", name="身份与冲突.md", exact=False).check()
        await page.get_by_role("button", name="追加整理", exact=True).click()
        await expect(page.locator(".update-summary")).to_contain_text("冲突 1", timeout=15000)
        await expect(page.locator(".update-summary")).to_contain_text("待核对 1")
        current = await (await page.request.get(base + "/knowledge")).json()
        process = next(c for c in current["concepts"] if c["name"] == "运行过程")
        assert process["id"] == old_process["id"] and not process.get("conflicts")
        threads = [c for c in current["concepts"] if c["name"] == "线程"]
        assert len(threads) == 2 and len({c["id"] for c in threads}) == 2
        thread = next(c for c in threads if c.get("conflicts"))
        assert thread["id"] == old_thread["id"]
        assert (await (await page.request.get(base + "/knowledge?version_id=" + before["version_id"])).json()) == before
        await page.get_by_role("button", name="全图", exact=True).click()
        await page.locator(".concept-list").get_by_role("button", name="运行体 · 待核对", exact=True).click()
        await expect(page.locator(".identity-review")).to_contain_text("无法确认")
        await page.locator(".concept-list").get_by_role("button", name="线程 · 有冲突", exact=True).click()
        await expect(page.locator(".concept-conflicts")).to_contain_text("相同模型")
        await expect(page.locator(".conflict-claim")).to_have_count(2)
        for index, needle in enumerate(["线程是进程中的一个执行单元", "线程不是处理机调度"]):
            await page.locator(".conflict-claim").nth(index).get_by_role("button").click()
            await expect(page.locator("dialog.source-dialog")).to_contain_text(needle)
            await page.locator("dialog.source-dialog").get_by_role("button", name="关闭", exact=True).click()
        await page.get_by_role("checkbox", name="中断后重试.md", exact=False).check()
        await page.get_by_role("button", name="追加整理", exact=True).click()
        await expect(page.locator(".task-panel.failed")).to_contain_text("受控页面输出截断", timeout=15000)
        assert (await (await page.request.get(base + "/knowledge")).json())["version_id"] == current["version_id"]
        await expect(page.locator(".concept-conflicts")).to_be_visible()
        await page.locator(".task-panel.failed").get_by_role("button", name="重试", exact=True).click()
        await expect(page.locator(".task-panel.completed")).to_be_visible(timeout=15000)
        await expect(page.locator(".update-summary")).to_contain_text("冲突 1")
        tasks = await (await page.request.get(base + "/tasks")).json()
        attempts = {step["name"]: step["attempts"] for step in tasks[0]["steps"]}
        assert attempts["extract"] == attempts["integrate"] == 1 and attempts["render"] == 2
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        await navigation.get_by_role("button").filter(has_text="整理失败（受控验收样本）").click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await expect(page.locator(".task-panel.failed")).to_be_visible()
        await expect(page.get_by_role("heading", name="尚未整理成课程知识", exact=True)).to_be_visible()
        await page.locator(".task-panel.failed").get_by_role("button", name="重试", exact=True).click()
        await expect(page.locator(".task-panel.completed")).to_be_visible(timeout=15000)
        await expect(page.locator(".graph-canvas canvas").first).to_be_visible()
        assert not errors, errors
        await browser.close()
    print("Identity browser passed: synonym identity, homonym separation, context distinction, uncertainty, conflict sides/sources, old version, first/incremental retry, mobile.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8026")
    parser.add_argument("--screenshot")
    asyncio.run(check(parser.parse_args()))
