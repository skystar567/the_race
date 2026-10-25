"""Identity and conflict behavior through the controlled public update flow."""

import copy

import pytest

from campus.jobs import Jobs
from campus.knowledge_models import ScopeInput
from campus.materials import Materials
from campus.scopes import resolve_scope
from test_incremental_knowledge import add_supplement, initial_course
from test_knowledge_api import ScriptedModel, client_for

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def conflict_supplement(data_dir, course_id, previous):
    material = Materials(data_dir).import_material(course_id, "冲突讲义.md",
        "# 资源分配\n\n在本讲义描述的操作系统中，进程不是资源分配的基本单位，线程才是。\n".encode())
    source = resolve_scope(Materials(data_dir), course_id, ScopeInput(material_ids=[material["id"]]))
    fragment = next(f for f in source["fragments"] if "进程不是" in f["markdown"])
    old = next(c for c in previous["concepts"] if c["name"] == "进程")
    new_citation = {"snippet_id": fragment["id"], "quote": "进程不是资源分配的基本单位"}
    old_citation = {"snippet_id": old["citations"][0]["snippet_id"], "quote": "是系统进行资源分配的基本单位"}
    extract = {"concepts": [{"key": "process", "name": "进程", "aliases": [],
        "definition": "关于资源分配单位的资料存在冲突，需对照双方说明。",
        "chapter_ids": [fragment["chapter_id"]], "citations": [new_citation]}], "relations": []}
    integrated = copy.deepcopy(extract)
    integrated["concepts"][0].update(existing_id=old["id"], identity_status="confirmed",
        identity_reason="两份资料均讨论操作系统进程的资源分配属性，身份一致但结论矛盾。",
        citations=[new_citation, old_citation],
        conflicts=[{"reason": "双方对同一语境下资源分配单位给出相反断言。", "claims": [
            {"statement": "进程是资源分配的基本单位。", "context": "教材的操作系统进程定义。", "citation": old_citation},
            {"statement": "进程不是资源分配的基本单位。", "context": "追加讲义讨论的操作系统。", "citation": new_citation},
        ]}])
    page = {"key": "process", "page_md": "资料对资源分配单位存在冲突，保留双方说明。\n\n" +
        "\n\n".join(f"{c['quote']}[原文](snippet:{c['snippet_id']})" for c in [old_citation, new_citation]),
        "citations": [old_citation, new_citation]}
    return material, {"抽取": extract, "整合": integrated, "Markdown 页面": {"pages": [page]}}


async def test_conflict_retains_both_claims_context_and_openable_sources(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    material, replies = conflict_supplement(tmp_path, course["id"], previous)
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    done = jobs.get(course["id"], task["id"])
    assert done["status"] == "completed", done["error_message"]
    async with client_for(tmp_path) as client:
        base = f"/api/courses/{course['id']}/knowledge"
        current = (await client.get(base)).json()
        assert current["summary"]["conflicts"] == 1
        old = next(c for c in previous["concepts"] if c["name"] == "进程")
        process = next(c for c in current["concepts"] if c["id"] == old["id"])
        conflict = process["conflicts"][0]
        assert conflict["id"] and len(conflict["claims"]) == 2
        assert {c["statement"] for c in conflict["claims"]} == {
            "进程是资源分配的基本单位。", "进程不是资源分配的基本单位。"}
        detail = (await client.get(base + f"/versions/{current['version_id']}/concepts/{process['id']}")).json()
        assert detail["conflicts"] == process["conflicts"]
        for claim in conflict["claims"]:
            assert claim["context"]
            response = await client.get(base + f"/versions/{current['version_id']}/sources/{claim['citation']['snippet_id']}")
            assert response.status_code == 200
            assert claim["citation"]["quote"] in response.json()["markdown"]
        assert (await client.get(base, params={"version_id": previous["version_id"]})).json() == previous
        assert all(relation in current["relations"] for relation in previous["relations"])


@pytest.mark.parametrize("case,name,definition,matched,status", [
    ("同义异名", "运行实例", "操作系统中程序的一次执行，也称进程。", True, "confirmed"),
    ("措辞不同", "进程", "进程是正在执行的程序实例。", True, "confirmed"),
    ("同名异义", "进程", "项目管理中的进程指项目推进阶段，与程序执行无关。", False, "confirmed"),
    ("语境不同", "进程", "在不支持线程的操作系统中，进程也是处理机调度的单位。", True, "confirmed"),
    ("身份不明", "进程", "本讲义提及进程，但尚未说明它是程序执行还是事件发展。", False, "needs_review"),
])
async def test_identity_decision_uses_meaning_without_mechanical_conflicts(tmp_path, case, name, definition, matched, status):
    course, _, previous = await initial_course(tmp_path)
    materials = Materials(tmp_path)
    material = materials.import_material(course["id"], case + ".md", ("# 补充术语\n\n" + definition + "\n").encode())
    source = resolve_scope(materials, course["id"], ScopeInput(material_ids=[material["id"]]))
    fragment = next(f for f in source["fragments"] if definition in f["markdown"])
    old = next(c for c in previous["concepts"] if c["name"] == "进程")
    citation = {"snippet_id": fragment["id"], "quote": definition}
    extract = {"concepts": [{"key": "candidate", "name": name, "aliases": [], "definition": definition,
        "chapter_ids": [fragment["chapter_id"]], "citations": [citation]}], "relations": []}
    integrated = copy.deepcopy(extract)
    concept = integrated["concepts"][0]
    concept.update(existing_id=old["id"] if matched else None, identity_status=status,
                   identity_reason=f"根据定义、适用语境及资料依据判断为{case}。", conflicts=[])
    if matched:
        concept["citations"] += copy.deepcopy(old["citations"])
    replies = {"抽取": extract, "整合": integrated, "Markdown 页面": {"pages": [
        {"key": "candidate", "page_md": f"{definition}[原文](snippet:{fragment['id']})", "citations": [citation]}]}}
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "completed"
    current = jobs.knowledge.snapshot(course["id"])
    assert current["summary"]["conflicts"] == 0
    assert len(current["concepts"]) == (2 if matched else 3)
    changed = next(c for c in current["concepts"] if c["definition"] == definition)
    assert changed["status"] == status
    assert (changed["id"] == old["id"]) == matched
    assert not changed["conflicts"]
    assert all(relation in current["relations"] for relation in previous["relations"])


@pytest.mark.parametrize("damage", ["missing_side", "blank_context", "same_source", "forged_old_quote", "foreign_source", "no_new_evidence"])
async def test_invalid_conflict_is_not_published(tmp_path, damage):
    course, _, previous = await initial_course(tmp_path)
    material, replies = conflict_supplement(tmp_path, course["id"], previous)
    conflict = replies["整合"]["concepts"][0]["conflicts"][0]
    if damage == "missing_side":
        conflict["claims"] = conflict["claims"][:1]
    elif damage == "blank_context":
        conflict["claims"][0]["context"] = "  "
    elif damage == "same_source":
        conflict["claims"][1]["citation"] = copy.deepcopy(conflict["claims"][0]["citation"])
    elif damage == "forged_old_quote":
        conflict["claims"][0]["citation"]["quote"] = "原文不含的伪造断言"
    elif damage == "foreign_source":
        _, _, foreign = await initial_course(tmp_path)
        conflict["claims"][0]["citation"] = copy.deepcopy(foreign["concepts"][0]["citations"][0])
    else:
        thread = next(c for c in previous["concepts"] if c["name"] == "线程")
        conflict["claims"][1]["citation"] = copy.deepcopy(thread["citations"][0])
        replies["整合"]["concepts"][0]["citations"] += copy.deepcopy(thread["citations"])
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "failed"
    assert jobs.knowledge.snapshot(course["id"]) == previous
    assert len(jobs.knowledge.versions(course["id"])) == 1


async def test_later_update_preserves_existing_conflicts_and_original_evidence(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    material, replies = conflict_supplement(tmp_path, course["id"], previous)
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    conflicted = jobs.knowledge.snapshot(course["id"])
    process = next(c for c in conflicted["concepts"] if c["name"] == "进程")
    material, _, replies = add_supplement(tmp_path, course["id"], conflicted)
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    assert jobs.get(course["id"], task["id"])["status"] == "completed"
    updated = jobs.knowledge.snapshot(course["id"])
    changed = next(c for c in updated["concepts"] if c["id"] == process["id"])
    assert changed["conflicts"] == process["conflicts"]
    assert updated["summary"]["conflicts"] == 1
    assert jobs.knowledge.snapshot(course["id"], conflicted["version_id"]) == conflicted


async def test_repeated_conflict_keeps_identity_despite_claim_order_or_rewording(tmp_path):
    course, _, previous = await initial_course(tmp_path)
    material, replies = conflict_supplement(tmp_path, course["id"], previous)
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    conflicted = jobs.knowledge.snapshot(course["id"])
    process = next(c for c in conflicted["concepts"] if c["name"] == "进程")
    repeated = {key: copy.deepcopy(value) for key, value in process["conflicts"][0].items() if key != "id"}
    repeated["reason"] = "相同原文的矛盾仍然存在，调整说明措辞。"
    repeated["claims"].reverse()
    repeated["claims"][0]["statement"] = "追加讲义否定进程是资源分配单位。"
    material, _, replies = add_supplement(tmp_path, course["id"], conflicted)
    replies["整合"]["concepts"][0]["conflicts"] = [repeated]
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    task = jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    done = jobs.get(course["id"], task["id"])
    assert done["status"] == "completed", done["error_message"]
    current = jobs.knowledge.snapshot(course["id"])
    changed = next(c for c in current["concepts"] if c["id"] == process["id"])
    assert current["summary"]["conflicts"] == 1
    assert changed["conflicts"] == process["conflicts"]


@pytest.mark.parametrize("damage", ["claim_quote", "summary", "duplicate_id", "duplicate_evidence"])
async def test_publication_rechecks_persisted_conflicts(tmp_path, damage):
    course, _, previous = await initial_course(tmp_path)
    material, replies = conflict_supplement(tmp_path, course["id"], previous)
    jobs = Jobs(tmp_path, model=ScriptedModel(replies))
    jobs.create(course["id"], ScopeInput(material_ids=[material["id"]]))
    await jobs.run_once()
    current = jobs.knowledge.snapshot(course["id"])
    bad = copy.deepcopy(current)
    concept = next(c for c in bad["concepts"] if c.get("conflicts"))
    if damage == "claim_quote":
        concept["conflicts"][0]["claims"][0]["citation"]["quote"] = "保存后被替换的伪造引用"
    elif damage == "summary":
        bad["summary"]["conflicts"] = 0
    else:
        concept["conflicts"].append(copy.deepcopy(concept["conflicts"][0]))
        if damage == "duplicate_evidence":
            concept["conflicts"][-1]["id"] = "different-id-for-the-same-conflict"
    with pytest.raises(ValueError):
        jobs.knowledge.publish_task(course["id"], "invalid-conflict-publication", bad,
                                    parent_version_id=current["version_id"])
    assert jobs.knowledge.snapshot(course["id"]) == current
