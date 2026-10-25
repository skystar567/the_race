"""Chapter navigation and viewport retention through browser-visible behavior."""

import argparse
import asyncio

from playwright.async_api import async_playwright, expect


async def check(args):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1480, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(args.url)
        await page.get_by_role("navigation", name="课程", exact=True).get_by_role("button").filter(has_text=args.course).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await expect(page.get_by_role("button", name="章节概览", exact=True)).to_have_attribute("aria-pressed", "true")
        await expect(page.locator(".concept-list button")).to_have_count(0)
        await page.get_by_role("button", name="展开 2.1 进程的定义", exact=True).click()
        await expect(page.locator(".concept-list")).to_contain_text("进程")
        await expect(page.locator(".concept-list")).not_to_contain_text("线程")
        await page.get_by_role("button", name="跨章节关联", exact=True).click()
        await expect(page.locator(".concept-list")).to_contain_text("线程")
        await expect(page.locator(".visible-relations")).to_contain_text("前置")
        await expect(page.locator(".visible-relations")).to_contain_text("系统推断")
        await page.get_by_role("button", name="全图", exact=True).click()
        canvas = page.locator(".graph-canvas")
        await canvas.scroll_into_view_if_needed()
        rendered = "nodes => nodes.map(canvas => canvas.toDataURL())"
        before_move = await canvas.locator("canvas").evaluate_all(rendered)
        box = await canvas.bounding_box()
        await page.mouse.move(box["x"] + 20, box["y"] + 20)
        await page.mouse.wheel(0, -240)
        await page.mouse.down()
        await page.mouse.move(box["x"] + 65, box["y"] + 55, steps=5)
        await page.mouse.up()
        await page.wait_for_timeout(300)
        positioned = await canvas.locator("canvas").evaluate_all(rendered)
        assert positioned != before_move, "Pan/zoom must visibly move the graph"
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        await page.locator(".concept-citations .citation").first.click()
        await expect(page.locator("dialog.source-dialog")).to_be_visible()
        await page.locator("dialog.source-dialog").get_by_role("button", name="关闭", exact=True).click()
        await page.get_by_role("button", name="关闭知识点页面", exact=True).click()
        await page.wait_for_timeout(300)
        assert await canvas.locator("canvas").evaluate_all(rendered) == positioned, "Returning from details must retain the rendered graph position"
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.get_by_role("button", name="章节概览", exact=True).click()
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        await browser.close()
    print("Chapter browser passed: overview, expansion, cross-chapter relations, full graph, pan/zoom retention, mobile.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8018")
    parser.add_argument("--course", default="操作系统（受控验收样本）")
    parser.add_argument("--screenshot")
    asyncio.run(check(parser.parse_args()))
