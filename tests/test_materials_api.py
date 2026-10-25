import httpx
import pytest

from campus.api import create_app


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client_for(data_dir):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(data_dir)), base_url="http://localhost"
    )


async def test_courses_can_be_created_and_read_after_restart(tmp_path):
    async with client_for(tmp_path) as client:
        response = await client.post("/api/courses", json={"name": "操作系统"})
        assert response.status_code == 201
        course = response.json()
        assert course["name"] == "操作系统"
        assert course["material_count"] == 0

    async with client_for(tmp_path) as restarted:
        assert (await restarted.get("/api/courses")).json() == [course]


async def test_import_preserves_original_and_keeps_courses_separate(tmp_path):
    original = "\ufeff## 第二章 进程\r\n\r\n进程是资源分配的单位。\r\n".encode()
    async with client_for(tmp_path) as client:
        course = (await client.post("/api/courses", json={"name": "操作系统"})).json()
        other = (await client.post("/api/courses", json={"name": "计算机网络"})).json()
        url = f"/api/courses/{course['id']}/materials"
        response = await client.post(url, params={"filename": "操作系统.md"}, content=original)
        assert response.status_code == 201
        material = response.json()
        assert material["filename"] == "操作系统.md"
        assert material["status"] == "imported"
        assert (await client.get(url)).json() == [material]
        assert (await client.get(f"/api/courses/{other['id']}/materials")).json() == []
        assert (await client.get(f"/api/courses/{other['id']}/materials/{material['id']}/raw")).status_code == 404

    async with client_for(tmp_path) as restarted:
        raw = await restarted.get(f"{url}/{material['id']}/raw")
        assert raw.content == original
        assert (await restarted.get(url)).json() == [material]
        counts = {c["id"]: c["material_count"] for c in (await restarted.get('/api/courses')).json()}
        assert counts == {course["id"]: 1, other["id"]: 0}


async def test_numbered_chapters_and_fragments_point_to_unchanged_original(tmp_path):
    original = ('## 第二章 进程\n\n## 2.1 程序执行\n\n## 2.1.1 前趋图\n\n'
                '进程之间存在前趋关系。\n\n![示意图](images/missing.png)\n\n'
                '```python\n## 不是章节\nprint("hello")\n```\n')
    async with client_for(tmp_path) as client:
        course = (await client.post('/api/courses', json={'name': '操作系统'})).json()
        base = f"/api/courses/{course['id']}/materials"
        material = (await client.post(base, params={'filename': '教材.md'}, content=original.encode())).json()
        url = f"{base}/{material['id']}"
        detail = await client.get(url)
        assert detail.status_code == 200
        chapters = detail.json()['chapters']
        assert [(c['title'], c['level'], c['start_line']) for c in chapters] == [
            ('第二章 进程', 1, 1), ('2.1 程序执行', 2, 3), ('2.1.1 前趋图', 3, 5)]
        assert chapters[1]['parent_id'] == chapters[0]['id']
        assert chapters[2]['parent_id'] == chapters[1]['id']
        fragments = (await client.get(url + '/fragments', params={'chapter_id': chapters[2]['id']})).json()
        paragraph = next(f for f in fragments if f['markdown'].strip() == '进程之间存在前趋关系。')
        assert (paragraph['start_line'], paragraph['end_line']) == (7, 7)
        assert detail.json()['missing_image_count'] == 1
        for f in fragments:
            assert f['markdown'] == ''.join(original.splitlines(keepends=True)[f['start_line']-1:f['end_line']])

    async with client_for(tmp_path) as restarted:
        same = (await restarted.get(url + '/fragments', params={'chapter_id': chapters[2]['id']})).json()
        assert [f['id'] for f in same] == [f['id'] for f in fragments]
        assert (await restarted.get(url + '/raw')).text == original


async def test_reading_renders_math_code_and_missing_images_without_active_html(tmp_path):
    text = ('# 公式与代码\n\n进程 $P_i$。\n\n$$\nP_i \\rightarrow P_j\n$$\n\n'
            '![前趋图](images/missing.png)\n\n```python\nprint("hello")\n```\n\n'
            '<script>alert(1)</script>\n')
    async with client_for(tmp_path) as client:
        course = (await client.post('/api/courses', json={'name': '操作系统'})).json()
        base = f"/api/courses/{course['id']}/materials"
        material = (await client.post(base, params={'filename': '公式.md'}, content=text.encode())).json()
        fragments = (await client.get(f"{base}/{material['id']}/fragments")).json()
        html = '\n'.join(f['html'] for f in fragments)
        assert 'data-math="P_i"' in html
        assert 'data-display="true"' in html
        assert 'P_i \\rightarrow P_j' in html
        assert '未导入图片' in html and '前趋图' in html
        assert '<img' not in html
        assert '<code class="language-python">' in html
        assert '<script>' not in html and '&lt;script&gt;' in html


async def test_app_serves_built_reader_and_rejects_cross_origin_writes(tmp_path):
    frontend = tmp_path / 'frontend'
    frontend.mkdir()
    (frontend / 'index.html').write_text('<html><title>课程学习空间</title></html>')
    (frontend / 'app.js').write_text('console.log("reader")')
    app = create_app(tmp_path / 'data', static_dir=frontend)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        assert (await client.get('/')).status_code == 200
        assert (await client.get('/app.js')).text == 'console.log("reader")'
        assert (await client.get('/api/unknown')).status_code == 404
        assert (await client.get('/%2e%2e/courses.sqlite3')).status_code == 404
        assert (await client.post('/api/courses', json={'name': '不应被创建'}, headers={'Origin': 'https://outside.example'})).status_code == 403
        assert (await client.get('/api/courses')).json() == []
        assert (await client.post('/api/courses', json={'name': '操作系统'}, headers={'Origin': 'http://localhost:8000'})).status_code == 201


async def test_local_numbering_restarts_under_a_new_chapter(tmp_path):
    text = '## 第二章 进程\n\n## 2.1.1 前趋图\n\n## 1. 定义\n\n说明。\n\n## 第三章 调度\n\n## 1. 概述\n'
    async with client_for(tmp_path) as client:
        course = (await client.post('/api/courses', json={'name': '操作系统'})).json()
        base = f"/api/courses/{course['id']}/materials"
        material = (await client.post(base, params={'filename': '章节.md'}, content=text.encode())).json()
        chapters = (await client.get(f"{base}/{material['id']}")).json()['chapters']
        assert [(c['title'],c['level']) for c in chapters] == [
            ('第二章 进程',1),('2.1.1 前趋图',3),('1. 定义',4),('第三章 调度',1),('1. 概述',2)]


@pytest.mark.parametrize('text,expected', [
    ('第一段\u2028仍是第一段\n\n# 下一章\n\n尾段。\n', '尾段。'),
    ('![前趋图][fig]\n\n[fig]: images/missing.png\n', '未导入图片'),
    ('$$x = 1$$ 所以答案为一。\n', '所以答案为一。'),
    ('$$\nx = 1\n\n+2\n$$\n', 'data-display="true"'),
])
async def test_reading_preserves_document_context_and_original_lines(tmp_path, text, expected):
    async with client_for(tmp_path) as client:
        course = (await client.post('/api/courses', json={'name': '边界资料'})).json()
        base = f"/api/courses/{course['id']}/materials"
        material = (await client.post(base, params={'filename': '边界.md'}, content=text.encode())).json()
        url = f"{base}/{material['id']}"
        fragments = (await client.get(url + '/fragments')).json()
        assert expected in '\n'.join(f['html'] for f in fragments)
        if '\u2028' in text:
            assert fragments[0]['markdown'] == '第一段\u2028仍是第一段\n'
            assert fragments[-1]['start_line'] == 5
        if '[fig]' in text:
            assert (await client.get(url)).json()['missing_image_count'] == 1
        assert (await client.get(url + '/raw')).content == text.encode()
