from pathlib import Path

import pytest

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_event import EventStrength, ObjectIdentity
from src.metadata_protocol import MetadataProtocol
from src.metadata_protocol_analyzer import analyze_function, analyze_source_file


ROOT = Path(__file__).parents[1]
PROTOCOL_E = (
    ROOT
    / "configs"
    / "metadata_protocols"
    / "protocol_e_allocation_lifecycle_v2.json"
)


def _protocol() -> MetadataProtocol:
    return MetadataProtocol.read_json(PROTOCOL_E)


def _function(tmp_path: Path, body: str):
    source = f"""
void *btrfs_get_parent(void *child)
{{
    struct btrfs_path *path;
    struct btrfs_path *other;
    int ret;
    {body}
}}
"""
    path = tmp_path / "allocation_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == "btrfs_get_parent")


def _function_without_path_declaration(tmp_path: Path, body: str):
    source = f"""
void *btrfs_get_parent(void *child)
{{
    struct btrfs_path *other;
    int ret;
    {body}
}}
"""
    path = tmp_path / "allocation_macro_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == "btrfs_get_parent")


def test_protocol_e_round_trip_preserves_allocation_summaries():
    protocol = _protocol()

    assert protocol.schema_version == 2
    assert protocol.protocol_id == "mocc.protocol_e.allocation_lifecycle"
    assert {item.summary_id for item in protocol.callee_summaries} == {
        "btrfs.search_path.alloc",
        "btrfs.search_path.free",
    }
    assert MetadataProtocol.from_json(protocol.to_json()).to_dict() == protocol.to_dict()


def test_alloc_then_free_is_legal_on_success(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    use_path(path);
    btrfs_free_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_alloc_then_free_is_legal_on_failure(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    ret = search(path);
    if (ret < 0) {
        btrfs_free_path(path);
        return ERR_PTR(ret);
    }
    btrfs_free_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_alloc_with_auto_free_macro_is_legal_on_return(tmp_path):
    function = _function(
        tmp_path,
        """
    BTRFS_PATH_AUTO_FREE(path);
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    use_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_auto_free_macro_declares_exact_path_object(tmp_path):
    function = _function_without_path_declaration(
        tmp_path,
        """
    BTRFS_PATH_AUTO_FREE(path);
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    use_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    opened = next(
        item for item in result.events if item["summary_id"] == "btrfs.search_path.alloc"
    )
    assert opened["object_ref"]["expression"] == "path"
    assert opened["object_ref"]["identity"] == ObjectIdentity.EXACT.value
    assert opened["strength"] == EventStrength.MUST.value
    assert not result.candidates
    assert not result.unknown


def test_manual_free_after_auto_free_macro_uses_exact_path_object(tmp_path):
    function = _function_without_path_declaration(
        tmp_path,
        """
    BTRFS_PATH_AUTO_FREE(path);
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    btrfs_free_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    freed = next(
        item for item in result.events if item["summary_id"] == "btrfs.search_path.free"
    )
    assert freed["object_ref"]["expression"] == "path"
    assert freed["object_ref"]["identity"] == ObjectIdentity.EXACT.value
    assert freed["strength"] == EventStrength.MUST.value
    assert not result.candidates
    assert not result.unknown


def test_alloc_returned_to_caller_is_legal_ownership_transfer(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return NULL;
    return path;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_allocated_member_of_returned_object_transfers_to_caller(tmp_path):
    source = """
struct holder {
    struct btrfs_path *path;
};

struct holder *btrfs_get_parent(void *child)
{
    struct holder *ret;

    ret = kzalloc_obj(*ret, 0);
    if (!ret)
        return NULL;

    ret->path = btrfs_alloc_path();
    if (!ret->path)
        return NULL;

    return ret;
}
"""
    path = tmp_path / "allocation_member_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    function = next(item for item in unit.functions if item.name == "btrfs_get_parent")

    result = analyze_function(function, _protocol())

    assert result is not None
    opened = next(
        item for item in result.events if item["summary_id"] == "btrfs.search_path.alloc"
    )
    assert opened["object_ref"]["expression"] == "ret->path"
    assert opened["object_ref"]["identity"] == ObjectIdentity.EXACT.value
    assert not result.candidates
    assert not result.unknown


def test_cleanup_label_free_is_legal_on_error_exit(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    ret = search(path);
    if (ret < 0)
        goto out_free_path;
    use_path(path);
out_free_path:
    btrfs_free_path(path);
    return ERR_PTR(ret);
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_macro_loop_break_to_implicit_exit_uses_later_free_epilogue(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    list_for_each_entry(other, child, list) {
        if (ret > 0)
            break;
    }
    btrfs_free_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_macro_loop_continue_to_implicit_exit_uses_later_free_epilogue(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    list_for_each_entry(other, child, list) {
        if (ret > 0)
            continue;
    }
    btrfs_free_path(path);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_macro_loop_implicit_exit_without_later_free_still_reports_open_path(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    list_for_each_entry(other, child, list) {
        if (ret > 0)
            break;
    }
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown


def test_alloc_without_free_reports_open_path(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown
    assert (
        result.candidates[0].open_effects[0]["spec_effect_id"]
        == "btrfs.search_path.allocation"
    )


def test_free_of_another_exact_path_does_not_close_allocation(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    btrfs_free_path(other);
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown


def test_unknown_free_object_is_analysis_unknown(tmp_path):
    function = _function(
        tmp_path,
        """
    path = btrfs_alloc_path();
    if (!path)
        return ERR_PTR(-12);
    btrfs_free_path(resolve_path());
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    freed = next(
        item
        for item in result.events
        if item["summary_id"] == "btrfs.search_path.free"
    )
    assert freed["object_ref"]["identity"] == ObjectIdentity.UNKNOWN.value
    assert freed["strength"] == EventStrength.MAY.value
    assert not result.candidates
    assert any(
        "compensation_summary_not_proven_must" in item.reasons
        for item in result.unknown
    )


def test_uncaptured_allocation_result_is_analysis_unknown(tmp_path):
    function = _function(
        tmp_path,
        """
    btrfs_alloc_path();
    return child;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert any("summary_result_not_captured" in item.reasons for item in result.unknown)


@pytest.mark.parametrize("version", ["6.8", "6.14", "7.1"])
def test_real_btrfs_parent_lookup_releases_path_in_supported_versions(version):
    result = analyze_source_file(
        str(
            ROOT
            / "linux-sources"
            / f"linux-v{version}-fs"
            / "fs"
            / "btrfs"
            / "export.c"
        ),
        _protocol(),
        source_version=f"linux-v{version}",
        function_names=["btrfs_get_parent"],
    )[0]

    assert not result.candidates
    assert not result.unknown
    assert {
        item["summary_id"]
        for item in result.events
        if item["summary_id"]
    } == {"btrfs.search_path.alloc", "btrfs.search_path.free"}
