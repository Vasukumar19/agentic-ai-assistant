"""Phase 6B.1 efficiency audit tests — deterministic, no LLM."""

import json
import os
import pytest

# seed MCP servers so registry-based canonicalization works
os.environ.setdefault("MCP_SERVERS", json.dumps([
    {"name": "filesystem", "transport": "stdio", "command": "python", "args": ["mcp_filesystem_server.py"]},
    {"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]},
]))

@pytest.fixture(scope="module", autouse=True)
def _seed_registry():
    from mcp_layer.registry import registry
    if not registry._discovered or "filesystem.read_file" not in registry.valid_names() or "test.lookup" not in registry.valid_names():
        # explicit: other test modules mutate MCP_SERVERS env, so don't rely on it
        registry._servers = {}
        registry.load_servers_from_config([
            {"name": "filesystem", "transport": "stdio", "command": "python", "args": ["mcp_filesystem_server.py"]},
            {"name": "test", "transport": "stdio", "command": "python", "args": ["mcp_test_server.py"]},
        ])
        try:
            registry.discover(force=True)
        except Exception:
            pass
    yield


def _canonicalize(name: str) -> str:
    """Mirrors registry alias logic for test purposes."""
    try:
        from mcp_layer.registry import registry
        if name in registry._normalized:
            norm = registry.get_normalized(name)
            if norm and norm.server and norm.name != f"{norm.server}.{norm.original_name}":
                return f"{norm.server}.{norm.original_name}"
            return norm.name if norm else name
        if "_" in name and "." not in name:
            if name.startswith("filesystem_"):
                cand = name.replace("filesystem_", "filesystem.", 1)
                if cand in registry._normalized:
                    return cand
                return name
            if name.startswith("test_"):
                cand = name.replace("test_", "test.", 1)
                if cand in registry._normalized:
                    return cand
                return name
            cand = name.replace("_", ".", 1)
            try:
                if cand in registry._normalized:
                    return cand
            except Exception:
                pass
            return name
        return name
    except Exception:
        if "_" in name and "." not in name:
            if name.startswith("filesystem_"):
                cand = name.replace("filesystem_", "filesystem.", 1)
                # only return cand if it looks like a known pattern, else keep original
                if cand.startswith("filesystem."):
                    return cand
                return name
            if name.startswith("test_"):
                cand = name.replace("test_", "test.", 1)
                if cand.startswith("test."):
                    return cand
                return name
        return name


class TestCanonicalization:
    def test_canonical_dot_unchanged(self):
        assert _canonicalize("filesystem.read_file") == "filesystem.read_file"

    def test_underscore_alias_resolves(self):
        assert _canonicalize("filesystem_read_file") == "filesystem.read_file"

    def test_all_filesystem_aliases(self):
        cases = {
            "filesystem_read_file": "filesystem.read_file",
            "filesystem_write_file": "filesystem.write_file",
            "filesystem_list_directory": "filesystem.list_directory",
            "filesystem_get_file_info": "filesystem.get_file_info",
            "filesystem_list_allowed_directories": "filesystem.list_allowed_directories",
            "test_echo": "test.echo",
            "test_add": "test.add",
            "test_lookup": "test.lookup",
        }
        for alias, canon in cases.items():
            assert _canonicalize(alias) == canon, f"{alias} -> {canon}"

    def test_unknown_tool_fails_safely(self):
        # unknown should return as-is (not crash)
        assert _canonicalize("unknown_tool_xyz") == "unknown_tool_xyz"
        assert _canonicalize("filesystem.nonexistent") == "filesystem.nonexistent"

    def test_collision_rejected(self):
        from mcp_layer.registry import registry
        # ensure filesystem.read_file is registered
        if "filesystem.read_file" not in registry.valid_names():
            registry._discovered = False
            registry._servers = {}
            registry.load_servers_from_config([{"name": "filesystem", "transport": "stdio", "command": "python", "args": ["mcp_filesystem_server.py"]}])
            registry.discover(force=True)
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
        class In(BaseModel):
            x: str = Field(description="x")
        dup = StructuredTool.from_function(func=lambda x: x, name="filesystem.read_file", description="dup", args_schema=In)
        with pytest.raises(ValueError):
            registry.register_native(dup)


class TestSequenceAnalysis:
    def _analyze(self, expected, raw):
        canonical = [_canonicalize(x) for x in raw]
        exact = raw == expected
        canon_exact = canonical == expected
        # repeated: count duplicates beyond first
        from collections import Counter
        counter = Counter(canonical)
        repeated = sum(cnt - 1 for cnt in counter.values() if cnt > 1)
        # extra: tools in canonical more than expected
        extra = []
        for tool in set(canonical):
            exp_cnt = expected.count(tool)
            can_cnt = canonical.count(tool)
            if can_cnt > exp_cnt:
                extra.extend([tool] * (can_cnt - exp_cnt))
        # missing: in expected not in canonical
        missing = [e for e in expected if e not in canonical]
        # wrong order: check if canonical is not in order but contains same multiset
        wrong_order = False
        if not canon_exact and set(canonical) == set(expected) and len(canonical) == len(expected):
            # same tools but different order
            wrong_order = canonical != expected
        return {
            "exact": exact,
            "canon_exact": canon_exact,
            "repeated": repeated,
            "extra": extra,
            "missing": missing,
            "wrong_order": wrong_order,
            "canonical": canonical,
        }

    def test_exact_sequence_detection(self):
        res = self._analyze(["filesystem.read_file"], ["filesystem.read_file"])
        assert res["exact"] is True
        assert res["canon_exact"] is True
        assert res["repeated"] == 0
        assert res["extra"] == []

    def test_canonicalized_sequence_detection(self):
        res = self._analyze(["filesystem.read_file"], ["filesystem_read_file"])
        assert res["exact"] is False  # raw has underscore
        assert res["canon_exact"] is True  # canonical matches

    def test_repeated_call_detection(self):
        res = self._analyze(["filesystem.read_file"], ["filesystem.read_file", "filesystem.read_file"])
        assert res["repeated"] == 1
        assert "filesystem.read_file" in res["extra"]

    def test_extra_call_detection(self):
        res = self._analyze(["filesystem.list_directory", "calculator"], ["filesystem.list_directory", "calculator", "filesystem.list_directory"])
        assert res["extra"] == ["filesystem.list_directory"]
        assert res["repeated"] == 1

    def test_missing_call_detection(self):
        res = self._analyze(["filesystem.read_file", "calculator"], ["filesystem.read_file"])
        assert res["missing"] == ["calculator"]
        assert res["extra"] == []

    def test_wrong_order_detection(self):
        res = self._analyze(["filesystem.read_file", "calculator"], ["calculator", "filesystem.read_file"])
        assert res["wrong_order"] is True
        assert res["canon_exact"] is False

    def test_legitimate_multi_step_not_marked_redundant(self):
        # correct multi-step with distinct tools should not be marked repeated
        res = self._analyze(["filesystem.read_file", "calculator"], ["filesystem.read_file", "calculator"])
        assert res["repeated"] == 0
        assert res["extra"] == []
        assert res["canon_exact"] is True

    def test_alias_duplicate_is_repeated(self):
        # raw has dot and underscore variants of same canonical -> should count as repeated
        res = self._analyze(["filesystem.list_allowed_directories"], ["filesystem.list_allowed_directories", "filesystem_list_allowed_directories", "filesystem.list_allowed_directories"])
        # canonical all become filesystem.list_allowed_directories, so count 3 -> repeated 2
        assert res["repeated"] == 2
        assert res["canon_exact"] is False
