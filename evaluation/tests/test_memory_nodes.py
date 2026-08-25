"""
Regression tests for the memory node bugs found in Phase 4:
1. Empty extractions must not wipe previously stored profile facts.
2. Confirmation message must not render empty fields or double phrasing.
"""

import json

import pytest

from nodes.memory_extractor import memory_response_node, memory_saver_node


@pytest.fixture
def mem_file(tmp_path, monkeypatch):
    import nodes.memory_extractor as mod
    p = tmp_path / "memory.json"
    monkeypatch.setattr(mod, "MEMORY_FILE", p)
    return p


def test_empty_extraction_does_not_wipe_profile(mem_file):
    mem_file.parent.mkdir(parents=True, exist_ok=True)
    mem_file.write_text(json.dumps({"name": "Vasu", "goal": "AI engineer"}))

    memory_saver_node({"extracted_profile": {"name": "", "goal": "", "profession": ""},
                       "extracted_semantic": []})

    saved = json.loads(mem_file.read_text())
    assert saved["name"] == "Vasu"
    assert saved["goal"] == "AI engineer"


def test_new_facts_still_merge(mem_file, tmp_path, monkeypatch):
    import nodes.memory_extractor as mod
    monkeypatch.setattr(mod, "SEMANTIC_MEMORY_DIR", tmp_path / "sem")

    memory_saver_node({"extracted_profile": {"name": "NewName"},
                       "extracted_semantic": []})

    saved = json.loads(mem_file.read_text())
    assert saved == {"name": "NewName"}


def test_confirmation_skips_empty_fields():
    out = memory_response_node({
        "extracted_profile": {"name": "", "goal": "", "profession": ""},
        "extracted_semantic": [],
    })
    # No blank-field artifacts like "your name is ," may appear.
    assert "your name is ," not in out["answer"]
    assert "is ." not in out["answer"]
    assert ", ," not in out["answer"]


def test_confirmation_no_doubled_goal_phrasing():
    out = memory_response_node({
        "extracted_profile": {"goal": "to become an AI engineer"},
        "extracted_semantic": [],
    })
    assert "to become an to become" not in out["answer"]
    assert "your goal is to become an AI engineer" in out["answer"]


def test_confirmation_plain_goal_and_name():
    out = memory_response_node({
        "extracted_profile": {"name": "Ada", "goal": "engineering excellence"},
        "extracted_semantic": [],
    })
    assert "your name is Ada" in out["answer"]
    assert "your goal is to become an engineering excellence" in out["answer"]
