"""Structured model outputs. Source locations are always supplied by the program."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(StrictModel):
    snippet_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class ConceptDraft(StrictModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str]
    definition: str = Field(min_length=1)
    chapter_ids: list[str]
    citations: list[Citation] = Field(min_length=1)


class RelationDraft(StrictModel):
    from_key: str
    to_key: str
    kind: Literal["precedes", "contrasts"]
    origin: Literal["source", "suggested"]
    citation: Citation | None
    reason: str = Field(min_length=1)


class KnowledgeDraft(StrictModel):
    concepts: list[ConceptDraft] = Field(min_length=1, max_length=80)
    relations: list[RelationDraft] = Field(max_length=300)


class ConflictClaim(StrictModel):
    statement: str = Field(min_length=1)
    context: str = Field(min_length=1)
    citation: Citation


class ConflictDraft(StrictModel):
    reason: str = Field(min_length=1)
    claims: list[ConflictClaim] = Field(min_length=2, max_length=8)


class ConflictRecord(ConflictDraft):
    id: str = Field(min_length=1)


class ConceptUpdate(ConceptDraft):
    existing_id: str | None = Field(min_length=1)
    identity_status: Literal["confirmed", "needs_review"]
    identity_reason: str = Field(min_length=1)
    conflicts: list[ConflictDraft] = Field(default_factory=list, max_length=20)


class KnowledgeUpdate(StrictModel):
    concepts: list[ConceptUpdate] = Field(min_length=1, max_length=80)
    relations: list[RelationDraft] = Field(max_length=300)


class PageDraft(StrictModel):
    key: str
    page_md: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class PagesDraft(StrictModel):
    pages: list[PageDraft] = Field(min_length=1)


class ScopeInput(StrictModel):
    material_ids: list[str] = Field(default_factory=list, max_length=100)
    chapter_ids: list[str] = Field(default_factory=list, max_length=500)
