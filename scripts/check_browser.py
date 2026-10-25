"""Verify ticket 01 through a running local app and a real browser."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from playwright.async_api import async_playwright, expect


@asynccontextmanager
async def delayed_response(page, pattern):
    arrived, release, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def delay(route):
        # Delay a real HTTP response; keep persistence and parsing real.
        response = await route.fetch()
        arrived.set()
        await release.wait()
        try:
            await route.fulfill(response=response)
        finally:
            completed.set()

    async def deliver():
        release.set()
        await asyncio.wait_for(completed.wait(), 10)

    await page.route(pattern, delay)
    try:
        yield arrived, deliver
    finally:
        release.set()
        await page.unroute(pattern, delay)


async def check_delayed_course_read(page, url, first_name, other_name):
    courses = await (await page.request.get(url + '/api/courses')).json()
    first_id = next(course['id'] for course in courses if course['name'] == first_name)
    pattern = url + f'/api/courses/{first_id}/materials/*/fragments*'
    navigation = page.get_by_role('navigation', name='课程', exact=True)
    async with delayed_response(page, pattern) as (arrived, deliver):
        await navigation.get_by_role('button').filter(has_text=first_name).click()
        await asyncio.wait_for(arrived.wait(), 10)
        await navigation.get_by_role('button').filter(has_text=other_name).click()
        await expect(page.get_by_text('网络课程独立资料。', exact=True)).to_be_visible()
        await deliver()
        await expect(page.get_by_role('heading', name=other_name, exact=True)).to_be_visible()
        await expect(page.get_by_role('button', name='验收样本.md')).to_have_count(0)
        await expect(page.get_by_role('alert')).to_have_count(0)


async def check_delayed_upload(page, url, first_name, other_name):
    courses = await (await page.request.get(url + '/api/courses')).json()
    other_id = next(course['id'] for course in courses if course['name'] == other_name)
    pattern = url + f'/api/courses/{other_id}/materials?*'
    navigation = page.get_by_role('navigation', name='课程', exact=True)
    async with delayed_response(page, pattern) as (arrived, deliver):
        await page.get_by_label('选择 Markdown 文件').set_input_files({'name': '延迟保存.md', 'mimeType': 'text/markdown', 'buffer': '# 网络补充资料\n\n后端已经保存。\n'.encode()})
        await asyncio.wait_for(arrived.wait(), 10)
        await navigation.get_by_role('button').filter(has_text=first_name).click()
        await expect(page.get_by_role('button', name='验收样本.md')).to_be_visible()
        await deliver()
        await expect(page.get_by_role('button', name='延迟保存.md')).to_have_count(0)
        await expect(page.get_by_role('alert')).to_have_count(0)
    await navigation.get_by_role('button').filter(has_text=other_name).click()
    await expect(page.get_by_role('button', name='延迟保存.md')).to_be_visible()
    await expect(navigation.get_by_role('button').filter(has_text=other_name)).to_contain_text('2 份学习资料')


async def check(args):
    text = '# 第二章 进程\n\n## 2.1 前趋图\n\n进程 $P_i$。\n\n![前趋图](images/missing.png)\n\n```python\nprint("hello")\n```\n'
    original = text.encode()
    suffix = uuid4().hex[:6]
    course_name, other_name = f'操作系统验收 {suffix}', f'网络验收 {suffix}'
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(args.url)
        await page.get_by_role('button', name='新建课程', exact=True).click()
        await page.get_by_label('课程名称').fill(course_name)
        await page.get_by_role('button', name='创建课程', exact=True).click()
        await expect(page.get_by_role('heading', name=course_name, exact=True)).to_be_visible()
        await page.get_by_label('选择 Markdown 文件').set_input_files({'name': '验收样本.md', 'mimeType': 'text/markdown', 'buffer': original})
        await expect(page.get_by_text('已导入 · 尚未整理', exact=True)).to_be_visible()
        await expect(page.locator('.missing-image')).to_contain_text('未导入图片')
        await expect(page.locator('.katex')).to_be_visible()
        await expect(page.locator('pre code')).to_contain_text('print("hello")')
        await page.get_by_role('button', name='2.1 前趋图', exact=True).click()
        await page.get_by_role('button', name='查看第 5 至 5 行原文').click()
        await expect(page.get_by_role('dialog')).to_contain_text('进程 $P_i$。')
        await page.get_by_role('button', name='关闭', exact=True).click()
        async with page.expect_download() as downloaded:
            await page.get_by_role('link', name='下载原始文件').click()
        download = await downloaded.value
        assert Path(await download.path()).read_bytes() == original
        await page.get_by_label('选择 Markdown 文件').set_input_files({'name': '无效资料.txt', 'mimeType': 'text/plain', 'buffer': b'not markdown'})
        await expect(page.get_by_role('alert')).to_contain_text('请选择 Markdown')
        await page.get_by_role('button', name='新建课程', exact=True).click()
        await expect(page.get_by_role('dialog').get_by_role('alert')).to_have_count(0)
        await page.get_by_label('课程名称').fill(other_name)
        await page.get_by_role('button', name='创建课程', exact=True).click()
        await expect(page.get_by_text('放入你的第一份学习资料')).to_be_visible()
        await expect(page.get_by_role('button', name='验收样本.md')).to_have_count(0)
        await expect(page.get_by_role('alert')).to_have_count(0)
        await page.get_by_label('选择 Markdown 文件').set_input_files({'name': '网络资料.md', 'mimeType': 'text/markdown', 'buffer': '# 网络\n\n网络课程独立资料。\n'.encode()})
        await expect(page.get_by_text('网络课程独立资料。', exact=True)).to_be_visible()
        await check_delayed_course_read(page, args.url, course_name, other_name)
        await check_delayed_upload(page, args.url, course_name, other_name)
        await page.get_by_role('navigation', name='课程', exact=True).get_by_role('button').filter(has_text=course_name).click()
        await page.reload()
        await expect(page.get_by_text('已导入 · 尚未整理', exact=True)).to_be_visible()
        if args.sample:
            await page.get_by_label('选择 Markdown 文件').set_input_files(args.sample)
            await expect(page.locator('.document-heading h2')).to_contain_text(Path(args.sample).stem)
        if args.screenshot:
            await page.screenshot(path=args.screenshot, full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 844})
        await expect(page.get_by_role('heading', name=course_name, exact=True)).to_be_visible()
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows'
        assert errors == [], errors
        await browser.close()
    print('Browser flow passed: create, import, chapters, math, code, missing images, source, download, error isolation, delayed course switch and upload, counts, reload, mobile.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='在单独的验收数据目录启动应用后执行；会创建两门测试课程。')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--sample', help='可选：额外上传真实教材样本')
    parser.add_argument('--screenshot', help='可选：保存桌面界面截图')
    asyncio.run(check(parser.parse_args()))
