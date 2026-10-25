"""Deterministic locatability checks, including truncated model quotes."""

import pytest

from campus.knowledge_models import Citation
from campus.knowledge_validation import citation_fragment_id, normalize_text

FRAGMENTS = {
    "s1": {
        "id": "s1",
        "markdown": "公式 $P_{1}\\rightarrow P_{2},\\ P_{2}\\rightarrow P_{5},\\ P_{3}\\rightarrow P_{5}$ 结束。",
    }
}


def test_exact_quote_is_located():
    citation = Citation(snippet_id="s1", quote="P_{1}\\rightarrow P_{2}")
    assert citation_fragment_id(citation, FRAGMENTS) == "s1"
    assert citation.quote == "P_{1}\\rightarrow P_{2}"


def test_truncated_formula_is_repaired_to_exact_prefix():
    citation = Citation(
        snippet_id="s1",
        quote="$P_{1}\\rightarrow P_{2},\\ P_{2}\\rightarrow P_{5}$",
    )
    assert citation_fragment_id(citation, FRAGMENTS) == "s1"
    assert normalize_text(citation.quote) in normalize_text(FRAGMENTS["s1"]["markdown"])
    assert citation.quote.endswith("P_{2}\\rightarrow P_{5}")


def test_unknown_quote_still_fails():
    citation = Citation(snippet_id="s1", quote="这段原文完全不存在")
    with pytest.raises(ValueError, match="引用文字与原文不符"):
        citation_fragment_id(citation, FRAGMENTS)
