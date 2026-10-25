"""Chapter navigation and viewport retention through browser-visible behavior."""

import argparse
import asyncio

from playwright.async_api import async_playwright, expect


# Inspect rendered pixels, not Cytoscape internals. One-pixel contour tolerance
# permits antialiasing changes after a canvas resize without hiding missing nodes.
RENDERED_GRAPH = """el => {
    const layers = [...el.querySelectorAll('canvas')];
    const canvas = document.createElement('canvas');
    canvas.width = layers[0].width; canvas.height = layers[0].height;
    const context = canvas.getContext('2d');
    for (const layer of layers.reverse()) context.drawImage(layer, 0, 0);
    const {width, height} = canvas;
    const pixels = context.getImageData(0, 0, width, height).data;
    const mask = new Array(width * height).fill('0');
    const fills = new Uint8Array(width * height);
    const edges = [0, 0, 0];
    const edgeColors = [[148,163,184], [29,78,216], [180,83,9]];
    const near = (i, color, tolerance) => color.every((v, c) => Math.abs(pixels[i+c]-v) <= tolerance);
    for (let p = 0; p < mask.length; p++) {
        const i = p * 4;
        if (pixels[i+3] < 128) continue;
        mask[p] = '1';
        if (near(i, [18,38,58], 3)) fills[p] = 1;
        else if (near(i, [255,247,237], 3)) fills[p] = 2;
        edgeColors.forEach((color, index) => { if (near(i, color, 8)) edges[index]++; });
    }
    let nodes = 0;
    for (let p = 0; p < fills.length; p++) {
        const color = fills[p];
        if (!color) continue;
        const queue = [p]; fills[p] = 0;
        for (let head = 0; head < queue.length; head++) {
            const q = queue[head];
            const adjacent = [q-width, q+width];
            if (q % width) adjacent.push(q-1);
            if (q % width < width-1) adjacent.push(q+1);
            for (const n of adjacent) {
                if (n >= 0 && n < fills.length && fills[n] === color) { fills[n] = 0; queue.push(n); }
            }
        }
        if (queue.length > 80) nodes++;
    }
    return {width, height, mask: mask.join(''), nodes, edges};
}"""


def assert_same_position(before, after):
    assert (before['width'], before['height']) == (after['width'], after['height'])
    assert before['nodes'] == after['nodes'] == 5, 'All five fixture nodes must stay visible'
    assert all(count > 10 for count in before['edges'] + after['edges']), 'Contains, precedes and contrasts must be drawn'
    width, height = before['width'], before['height']
    for source, target in ((before['mask'], after['mask']), (after['mask'], before['mask'])):
        for index, value in enumerate(source):
            if value != '1' or target[index] == '1':
                continue
            x, y = index % width, index // width
            assert any(target[row * width + column] == '1'
                       for row in range(max(0, y-1), min(height, y+2))
                       for column in range(max(0, x-1), min(width, x+2))), 'Returning from details moved or removed graph content'


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
        # A chapter remembered as expanded must still open from other views.
        for mode in ("全图", "跨章节关联"):
            await page.get_by_role("button", name=mode, exact=True).click()
            await page.get_by_role("button", name="展开 2.1 进程的定义", exact=True).click()
            await expect(page.get_by_role("button", name="收起 2.1 进程的定义", exact=True)).to_have_attribute("aria-expanded", "true")
            await expect(page.locator(".concept-list").get_by_role("button", name="进程", exact=True)).to_be_visible()
        await page.get_by_role("button", name="全图", exact=True).click()
        await page.get_by_role("button", name="适应画布", exact=True).click()
        canvas = page.locator(".graph-canvas")
        await canvas.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        before_move = await canvas.evaluate(RENDERED_GRAPH)
        box = await canvas.bounding_box()
        await page.mouse.move(box["x"] + 20, box["y"] + 20)
        await page.mouse.wheel(0, -120)
        await page.mouse.down()
        await page.mouse.move(box["x"] + 65, box["y"] + 55, steps=5)
        await page.mouse.up()
        await page.wait_for_timeout(300)
        positioned = await canvas.evaluate(RENDERED_GRAPH)
        assert positioned['mask'] != before_move['mask'], "Pan/zoom must visibly move the graph"
        await page.locator(".concept-list").get_by_role("button", name="进程", exact=True).click()
        await expect(page.locator(".concept-panel-head h2")).to_have_text("进程")
        await expect(page.locator(".concept-page .katex")).to_be_visible()
        await expect(page.locator(".concept-page pre code")).to_contain_text('print("render fixture")')
        await expect(page.locator(".concept-page .missing-image")).to_contain_text("process-fixture.png")
        await page.locator(".concept-citations .citation").first.click()
        await expect(page.locator("dialog.source-dialog")).to_be_visible()
        await page.locator("dialog.source-dialog").get_by_role("button", name="关闭", exact=True).click()
        await page.get_by_role("button", name="关闭知识点页面", exact=True).click()
        await page.wait_for_timeout(300)
        assert_same_position(positioned, await canvas.evaluate(RENDERED_GRAPH))
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
