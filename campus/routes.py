"""Deterministic prerequisite routes over one published snapshot."""

from __future__ import annotations

from heapq import heappop, heappush
from typing import Any

from .knowledge import Knowledge


def _cycles(nodes: set[str], children: dict[str, list[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[list[str]] = []

    def visit(node: str):
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for child in children.get(node, []):
            if child not in nodes:
                continue
            if child not in indices:
                visit(child)
                low[node] = min(low[node], low[child])
            elif child in on_stack:
                low[node] = min(low[node], indices[child])
        if low[node] == indices[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.discard(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                result.append(sorted(component))
            elif component[0] in children.get(component[0], []):
                result.append(component)

    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return sorted(result, key=lambda item: (len(item), item))


def _ancestors(target: str, parents: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [target]
    while stack:
        node = stack.pop()
        for parent in parents.get(node, []):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def _ordered(nodes: set[str], parents: dict[str, list[str]], cyclic: set[str]) -> list[str]:
    indegree = {node: 0 for node in nodes}
    children: dict[str, list[str]] = {}
    for node in nodes:
        for parent in parents.get(node, []):
            if parent in nodes and parent not in cyclic:
                indegree[node] += 1
                children.setdefault(parent, []).append(node)
    heap = [(node, node) for node in nodes if indegree[node] == 0]
    heap.sort()
    result = []
    while heap:
        _, node = heappop(heap)
        result.append(node)
        for child in sorted(children.get(node, [])):
            indegree[child] -= 1
            if indegree[child] == 0:
                heappush(heap, (child, child))
    return result


def build_route(snapshot: dict[str, Any], target: str, current: str | None = None) -> dict[str, Any]:
    concepts = {concept["id"]: concept for concept in snapshot["concepts"]}
    if target not in concepts:
        raise LookupError("目标知识点不存在。")
    pages = {concept["id"] for concept in snapshot["concepts"] if concept.get("page_md")}
    edges = [relation for relation in snapshot["relations"] if relation["kind"] == "precedes"]
    parents: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {}
    for edge in edges:
        parents.setdefault(edge["to_id"], []).append(edge["from_id"])
        children.setdefault(edge["from_id"], []).append(edge["to_id"])
    relevant = _ancestors(target, parents) | {target}
    available = {node for node in relevant if node in concepts}
    missing = relevant - available
    cycles = [cycle for cycle in _cycles(relevant, children) if set(cycle) & available]
    cyclic = {node for cycle in cycles for node in cycle}
    target_blocked = target in cyclic
    gaps = [
        {"node": node, "required_by": sorted({edge["to_id"] for edge in edges
                                               if edge["from_id"] == node and edge["to_id"] in relevant}),
         "reason": "missing"}
        for node in sorted(missing)
    ]
    gaps.extend({"node": concept_id, "required_by": [concept_id], "reason": "missing-page"}
                for concept_id in sorted(relevant & set(concepts))
                if concept_id not in pages and concept_id not in cyclic)
    unverified = [
        {"from": edge["from_id"], "to": edge["to_id"], "reason": "suggested"}
        for edge in edges
        if edge["from_id"] in available and edge["to_id"] in available and edge.get("origin") == "suggested"
    ]

    prior = []
    current_related = True
    if current:
        if current not in concepts:
            raise LookupError("当前学习位置不存在。")
        current_related = current in relevant
        prior_set = (_ancestors(current, parents) | {current}) & available
        prior = _ordered(prior_set, parents, cyclic)
    prior_set = set(prior)
    order = _ordered(available - cyclic - prior_set, parents, cyclic)
    if not target_blocked and target not in order and target not in prior_set:
        order.append(target)
    order = [node for node in order if node not in prior_set]

    excluded = [
        {"from": relation["from_id"], "to": relation["to_id"],
         "type": relation["kind"], "reason": "not-prerequisite"}
        for relation in snapshot["relations"]
        if relation["kind"] != "precedes"
        and (relation["from_id"] in relevant or relation["to_id"] in relevant)
    ]
    warnings = []
    if target_blocked:
        warnings.append("目标知识点位于循环中，无法确定完整学习顺序。")
    if cycles:
        warnings.append("检测到前置循环。")
    if gaps:
        warnings.append("存在缺失的知识点或页面，路线不完整。")
    if unverified:
        warnings.append("部分前置关系为系统建议，不是原文明确顺序。")
    if current and not current_related:
        warnings.append("当前学习位置不在目标的已确定前置链上，已按完整路线展示。")
    status = ("blocked" if target_blocked else
              "partial" if cycles or gaps or unverified or (current and not current_related)
              else "complete")
    return {
        "version_id": snapshot["version_id"], "target": target, "current": current,
        "status": status, "route": [] if target_blocked else order, "prior": prior,
        "cycles": cycles, "gaps": gaps, "unverified": unverified,
        "excluded_relations": excluded, "warnings": warnings,
    }


class RouteService:
    def __init__(self, knowledge: Knowledge):
        self.knowledge = knowledge

    def plan(self, course_id: str, target: str, current: str | None = None,
             version_id: str | None = None) -> dict[str, Any]:
        snapshot = self.knowledge.snapshot(course_id, version_id)
        if snapshot is None:
            raise LookupError("课程还没有已发布知识版本。")
        return build_route(snapshot, target, current)
