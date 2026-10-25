"""Read-only browser verification of retained answers, notes and their sources."""

import argparse
import asyncio

from playwright.async_api import async_playwright, expect


async def check(args):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1480, "height": 1000})
        errors, writes = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))

        async def read_only(route):
            if route.request.method not in {"GET", "HEAD", "OPTIONS"}:
                writes.append(route.request.url)
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/api/**", read_only)

        async def get(url):
            response = await page.request.get(url)
            assert response.ok, (url, response.status)
            return await response.json()

        courses = await get(args.url + "/api/courses")
        course = next(c for c in courses if c["name"] == args.course)
        base = args.url + f"/api/courses/{course['id']}"
        snapshot = await get(base + "/knowledge")
        answers = await get(base + "/answers")
        notes = await get(base + "/notes")
        assert answers and notes, "Requires retained answers and notes."
        source_count = 0

        async def source_check(citation, version, button):
            nonlocal source_count
            source = await get(args.url + citation["source_url"])
            assert source["version_id"] == version
            raw = await page.request.get(base + f"/materials/{source['material_id']}/raw")
            assert raw.ok
            lines = (await raw.text()).splitlines(keepends=True)
            assert source["markdown"] == "".join(lines[source["start_line"] - 1:source["end_line"]])
            await button.click()
            dialog = page.get_by_role("dialog", name="原文依据", exact=True)
            await expect(dialog).to_be_visible()
            await expect(dialog.locator(".source-meta")).to_contain_text(version[:8])
            await dialog.locator("summary").click()
            await expect(dialog.locator(".source-original")).to_have_text(source["markdown"])
            await dialog.get_by_role("button", name="关闭", exact=True).click()
            source_count += 1

        await page.goto(args.url)
        await page.get_by_role("navigation", name="课程", exact=True).get_by_role("button").filter(has_text=course["name"]).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="课程提问", exact=True).click()
        qa = page.get_by_role("complementary", name="课程问答", exact=True)
        # The product displays its six most recent answers.
        for index, item in enumerate(answers[:6]):
            detail = await get(base + f"/answers/{item['id']}")
            await qa.locator(".qa-history-item").nth(index).click()
            await expect(qa.get_by_label("课程问题", exact=True)).to_have_value(detail["question"])
            await expect(qa.locator(f".qa-answer .badge.{detail['status']}")).to_be_visible()
            await expect(qa.locator(".answer-citations .citation")).to_have_count(len(detail["citations"]))
            await expect(qa.locator(".qa-answer-head")).to_contain_text(detail["version_id"][:8])
            if detail["text"]:
                await expect(qa.locator(".answer-body")).not_to_be_empty()
            for number, citation in enumerate(detail["citations"]):
                await source_check(citation, detail["version_id"], qa.locator(".answer-citations .citation").nth(number))
        await qa.get_by_role("button", name="关闭课程问答").click()
        await page.get_by_role("button", name="个人笔记", exact=True).click()
        for item in notes:
            detail = await get(base + f"/notes/{item['id']}")
            await page.locator(".note-item").filter(has=page.locator(".note-item-title", has_text=detail["title"])).click()
            await expect(page.get_by_label("笔记标题", exact=True)).to_have_value(detail["title"])
            await page.locator(".note-editor").get_by_role("button", name="编辑", exact=True).click()
            await expect(page.get_by_label("笔记正文", exact=True)).to_have_value(detail["body_md"])
            if detail["expansion"]:
                await expect(page.locator(".note-meta .badge.expansion")).to_be_visible()
                assert "模型补充" in detail["body_md"]
            for number, citation in enumerate(detail["citations"]):
                await source_check(citation, detail["version_id"], page.locator(".note-citations .citation").nth(number))
        await page.reload()
        await page.get_by_role("button", name="个人笔记", exact=True).click()
        await expect(page.locator(".note-item")).to_have_count(len(notes))
        await page.set_viewport_size({"width": 390, "height": 844})
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        assert await get(base + "/knowledge") == snapshot
        assert await get(base + "/answers") == answers
        assert await get(base + "/notes") == notes
        assert not errors, errors
        assert not writes, writes
        await browser.close()
        print(f"Read-only study check passed: {min(6, len(answers))} answers, {len(notes)} notes, {source_count} source openings; reload and mobile; no writes/model calls.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--course", required=True)
    parser.add_argument("--screenshot")
    asyncio.run(check(parser.parse_args()))
