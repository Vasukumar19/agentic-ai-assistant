"""
Agent-level memory evaluation (Section 9 of Phase 4 spec).

Tests write -> retrieval -> update -> preservation -> conflict/update
through the FULL agent graph.  Not leaked into production logic.

These tests exercise the same code paths as p4_mem_01-06 in the benchmark
but verify specific behavioral requirements the benchmark only checks indirectly.
"""

import pytest

from config import MEMORY_FILE, SEMANTIC_MEMORY_DIR


@pytest.fixture(autouse=True)
def _isolated_memory(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(config, "SEMANTIC_MEMORY_DIR", tmp_path / "semantic")
    yield


@pytest.fixture(scope="module")
def _agent():
    from graph import create_runnable_graph
    return create_runnable_graph()


def _ans(out):
    return (out.get("answer") or "").lower()


class TestMemoryWriteAndRetrieval:
    def test_write_name_retrieve(self, _agent):
        w = _ans(_agent.invoke({"question": "Remember that my name is Vasu."}))
        assert "vasu" in w
        r = _ans(_agent.invoke({"question": "What is my name?"}))
        assert "vasu" in r

    def test_write_goal_retrieve(self, _agent):
        w = _ans(_agent.invoke({"question": "Remember that my goal is to become an AI engineer."}))
        assert "ai engineer" in w
        r = _ans(_agent.invoke({"question": "What is my goal?"}))
        assert "ai engineer" in r


class TestMemoryUpdate:
    def test_language_replaces(self, _agent):
        _ans(_agent.invoke({"question": "Remember that my favorite programming language is Python."}))
        _ans(_agent.invoke({"question": "Remember that my favorite programming language is Rust."}))
        r = _ans(_agent.invoke({"question": "What is my favorite programming language?"}))
        assert "rust" in r


class TestMemoryPreservation:
    def test_new_field_preserves_existing(self, _agent):
        _ans(_agent.invoke({"question": "Remember that my name is Ada."}))
        _ans(_agent.invoke({"question": "Remember that my favorite programming language is Rust."}))
        name_r = _ans(_agent.invoke({"question": "What is my name?"}))
        assert "ada" in name_r
        lang_r = _ans(_agent.invoke({"question": "What is my favorite programming language?"}))
        assert "rust" in lang_r


class TestMemoryConflict:
    def test_overwrite_final_wins(self, _agent):
        _ans(_agent.invoke({"question": "Remember that my goal is to become a data scientist."}))
        _ans(_agent.invoke({"question": "Remember that my goal is to become an AI engineer."}))
        r = _ans(_agent.invoke({"question": "What is my goal?"}))
        assert "ai engineer" in r
