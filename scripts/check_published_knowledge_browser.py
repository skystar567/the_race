"""Read an existing real knowledge version in Chromium; never call the model.

Use after a credentialed build. This checks navigation and provenance; a human
must still compare definitions and relations with the textbook for correctness.
"""

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
        course = next(item for item in courses if item["name"] == args.course)
        base = args.url + f"/api/courses/{course['id']}/knowledge"
        snapshot = await (await page.request.get(base)).json()
        assert snapshot["state"] == "published" and snapshot["concepts"]
        version = snapshot["version_id"]
        await page.goto(args.url)
        await page.get_by_role("navigation", name="课程", exact=True).get_by_role("button").filter(has_text=args.course).click()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        if args.verify_chapter_scope:
            await expect(page.get_by_role("button", name="章节概览", exact=True)).to_have_attribute("aria-pressed", "true")
            coverage = await (await page.request.get(base + "/coverage?version_id=" + version)).json()
            assert coverage["version_id"] == version
            chapter_rows = {chapter["id"]: chapter for material in coverage["materials"] for chapter in material["chapters"]}
            selected_chapters = snapshot["selection"]["chapter_ids"]
            assert len(selected_chapters) >= 2
            assert all(chapter_rows[chapter_id]["status"] == "organized" for chapter_id in selected_chapters)
            unorganized = [material for material in coverage["materials"] if material["status"] == "unorganized"]
            assert unorganized, "The real acceptance course must retain unprocessed material"
            await page.locator(".coverage-panel summary").click()
            for material in unorganized:
                await expect(page.locator(".coverage-material").filter(has_text=material["filename"])).to_contain_text("尚未整理")
            await page.locator(".coverage-panel summary").click()
            chapters = {chapter["id"]: chapter for chapter in snapshot["chapters"]}
            shared = [concept for concept in snapshot["concepts"] if len({chapters[cid]["material_id"] for cid in concept["chapter_ids"]}) >= 2]
            assert shared, "Real definitions and applications must share at least one knowledge identity"
            # Expanding both selected sections must expose one button per shared identity.
            for chapter_id in selected_chapters:
                await page.get_by_role("button", name="展开 " + chapter_rows[chapter_id]["title"], exact=True).click()
            for concept in shared:
                await expect(page.locator(".concept-list").get_by_role("button", name=concept["name"], exact=True)).to_have_count(1)
            await page.get_by_role("button", name="跨章节关联", exact=True).click()
            for concept in shared:
                await expect(page.locator(".concept-list").get_by_role("button", name=concept["name"], exact=True)).to_have_count(1)
        await page.get_by_role("button", name="全图", exact=True).click()
        await expect(page.locator(".graph-canvas canvas").first).to_be_visible()
        for concept in snapshot["concepts"]:
            detail = await (await page.request.get(base + f"/versions/{version}/concepts/{concept['id']}")).json()
            assert detail["version_id"] == version
            await page.locator(".concept-list").get_by_role("button", name=concept["name"], exact=True).click()
            await expect(page.locator(".concept-panel-head h2")).to_have_text(concept["name"])
            await expect(page.locator(".concept-page")).not_to_be_empty()
            for index, citation in enumerate(detail["citations"]):
                source = await (await page.request.get(base + f"/versions/{version}/sources/{citation['snippet_id']}")).json()
                assert source["version_id"] == version
                raw = await (await page.request.get(args.url + f"/api/courses/{course['id']}/materials/{source['material_id']}/raw")).text()
                lines = raw.splitlines(keepends=True)
                assert source["markdown"] == "".join(lines[source["start_line"] - 1:source["end_line"]])
                await page.locator(".concept-citations .citation").nth(index).click()
                dialog = page.locator("dialog.source-dialog")
                await expect(dialog).to_be_visible()
                await expect(dialog.locator(".source-meta")).to_contain_text(source["filename"])
                await dialog.locator("summary").click()
                await expect(dialog.locator(".source-original")).to_have_text(source["markdown"])
                await dialog.get_by_role("button", name="关闭", exact=True).click()
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        await page.reload()
        await page.get_by_role("button", name="知识图谱", exact=True).click()
        await page.get_by_role("button", name="全图", exact=True).click()
        await expect(page.locator(".concept-list button")).to_have_count(len(snapshot["concepts"]))
        reopened = await (await page.request.get(base)).json()
        assert reopened["version_id"] == version
        assert [c["id"] for c in reopened["concepts"]] == [c["id"] for c in snapshot["concepts"]]
        await page.set_viewport_size({"width": 390, "height": 844})
        await expect(page.locator(".graph-canvas canvas").first).to_be_visible()
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        await browser.close()
        print(f"Published knowledge verified: {len(snapshot['concepts'])} pages, all citations, version {version}, reload, mobile; no model calls.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="读取已发布知识，核查页面、原文定位和重新打开后的版本。")
    parser.add_argument("--url", default="http://127.0.0.1:8017")
    parser.add_argument("--course", required=True)
    parser.add_argument("--screenshot")
    parser.add_argument("--verify-chapter-scope", action="store_true", help="同时核查真实多章节范围及跨资料的概念身份")
    asyncio.run(check(parser.parse_args()))
