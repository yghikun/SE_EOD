from pathlib import Path

import pytest

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.residual_slicer import slice_function_residuals
from src.transient_provenance import infer_transient_argument_provenance


def _functions(tmp_path: Path, source: str):
    path = tmp_path / "provenance.c"
    path.write_text(source, encoding="utf-8")
    return tuple(TreeSitterFrontend(tmp_path).parse(path).functions)


def _proven_parameters(functions, callee="work"):
    function = next(item for item in functions if item.name == callee)
    evidence = infer_transient_argument_provenance(functions).get(function.function_id, ())
    return {item.parameter for item in evidence}, evidence


def test_accepts_all_calls_with_type_compatible_automatic_aggregates(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
int work(struct operation *arg) { arg->type = 1; return fail_metadata(); }
int caller1(void) { struct operation one; return work(&one); }
int caller2(void) { struct operation two; return work(&(two)); }
""",
    )

    parameters, evidence = _proven_parameters(functions)

    assert parameters == {"arg"}
    assert {item.caller_local for item in evidence} == {"one", "two"}


@pytest.mark.parametrize(
    "declaration,argument",
    [
        ("struct operation *pointer", "pointer"),
        ("struct operation *pointer = alloc_operation()", "pointer"),
        ("struct other other", "&other"),
    ],
)
def test_rejects_nonautomatic_or_type_mismatched_arguments(
    tmp_path: Path, declaration: str, argument: str
):
    functions = _functions(
        tmp_path,
        f"""
struct operation {{ int type; }}; struct other {{ int type; }};
int work(struct operation *arg) {{ arg->type = 1; return fail_metadata(); }}
int caller(void) {{ {declaration}; return work({argument}); }}
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_rejects_when_any_call_uses_a_caller_parameter(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
int work(struct operation *arg) { arg->type = 1; return fail_metadata(); }
int local_caller(void) { struct operation local; return work(&local); }
int borrowed_caller(struct operation *borrowed) { return work(borrowed); }
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_rejects_static_local_storage(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
int work(struct operation *arg) { arg->type = 1; return 0; }
int caller(void) { static struct operation local; return work(&local); }
""",
    )

    assert _proven_parameters(functions)[0] == set()


@pytest.mark.parametrize(
    "publication",
    [
        "global_operation = &local;",
        "holder->operation = &local;",
        "return &local;",
    ],
)
def test_rejects_caller_local_address_publication(tmp_path: Path, publication: str):
    functions = _functions(
        tmp_path,
        f"""
struct operation {{ int type; }};
struct holder {{ struct operation *operation; }};
struct operation *global_operation;
int work(struct operation *arg) {{ arg->type = 1; return fail_metadata(); }}
struct operation *caller(struct holder *holder) {{
    struct operation local;
    work(&local);
    {publication}
    return 0;
}}
""",
    )

    assert _proven_parameters(functions)[0] == set()


@pytest.mark.parametrize(
    "publication",
    [
        "global_operation = arg;",
        "holder->operation = arg;",
        "return arg;",
    ],
)
def test_rejects_callee_parameter_publication(tmp_path: Path, publication: str):
    functions = _functions(
        tmp_path,
        f"""
struct operation {{ int type; }};
struct holder {{ struct operation *operation; }};
struct operation *global_operation;
struct operation *work(struct operation *arg, struct holder *holder) {{
    arg->type = 1;
    {publication}
    return 0;
}}
int caller(struct holder *holder) {{ struct operation local; work(&local, holder); return 0; }}
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_rejects_transitive_local_alias_publication(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
struct operation *global_operation;
int work(struct operation *arg) {
    struct operation *alias = arg;
    global_operation = alias;
    return 0;
}
int caller(void) { struct operation local; return work(&local); }
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_rejects_transitive_caller_alias_publication(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
struct operation *global_operation;
int work(struct operation *arg) { return 0; }
int caller(void) {
    struct operation local;
    struct operation *alias = &local;
    work(&local);
    global_operation = alias;
    return 0;
}
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_accepts_visible_synchronous_borrow_chain(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
static int inspect(struct operation *arg) { return arg->type; }
int work(struct operation *arg) { return inspect(arg); }
int caller(void) { struct operation local; return work(&local); }
""",
    )

    assert _proven_parameters(functions)[0] == {"arg"}


def test_opaque_helper_call_is_not_itself_publication_evidence(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
int work(struct operation *arg) { return opaque_helper(arg); }
int caller(void) { struct operation local; return work(&local); }
""",
    )

    assert _proven_parameters(functions)[0] == {"arg"}


def test_rejects_visible_helper_that_publishes(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
struct operation *global_operation;
static int publish(struct operation *arg) { global_operation = arg; return 0; }
int work(struct operation *arg) { return publish(arg); }
int caller(void) { struct operation local; return work(&local); }
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_rejects_container_field_publication_through_visible_helper(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct operation { int type; };
struct wrapper { struct operation *operation; };
struct operation *global_operation;
static int publish_wrapper(struct wrapper *wrapper) {
    global_operation = wrapper->operation;
    return 0;
}
int work(struct operation *arg) {
    struct wrapper wrapper = { .operation = arg };
    return publish_wrapper(&wrapper);
}
int caller(void) { struct operation local; return work(&local); }
""",
    )

    assert _proven_parameters(functions)[0] == set()


def test_rejects_ambiguous_same_name_definitions(tmp_path: Path):
    first = _functions(
        tmp_path,
        """
struct operation { int type; };
static int work(struct operation *arg) { return 0; }
int caller(void) { struct operation local; return work(&local); }
""",
    )
    second_path = tmp_path / "second.c"
    second_path.write_text(
        "struct operation { int type; }; static int work(struct operation *arg) { return 0; }",
        encoding="utf-8",
    )
    functions = first + tuple(
        TreeSitterFrontend(tmp_path).parse(second_path).functions
    )

    assert infer_transient_argument_provenance(functions) == {}


def test_slicer_excludes_only_exact_parameter_root(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct inode { long i_blocks; };
struct xfs_name { int type; struct inode *inode; };
int work(struct xfs_name *src_name) {
    int ret;
    src_name->type = XFS_DIR3_FT_CHRDEV;
    src_name->inode->i_blocks += 1;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
int caller(void) { struct xfs_name local; return work(&local); }
""",
    )
    work = next(item for item in functions if item.name == "work")
    provenance = infer_transient_argument_provenance(functions)[work.function_id]

    result = slice_function_residuals(work, transient_provenance=provenance)

    residual_slice = result.slices[0]
    assert [(item.root, item.key) for item in residual_slice.out_of_scope_effects] == [
        ("src_name", "type")
    ]
    assert any(item.key == "i_blocks" for item in residual_slice.residuals)
    assert residual_slice.out_of_scope_effects[0].transient_provenance == provenance


def test_slicer_keeps_name_inferred_helper_effect_on_transient_parameter(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
struct xfs_name { int type; };
int quota_charge(struct xfs_name *src_name) { return 0; }
int work(struct xfs_name *src_name) {
    int ret;
    quota_charge(src_name);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
int caller(void) { struct xfs_name local; return work(&local); }
""",
    )
    work = next(item for item in functions if item.name == "work")
    provenance = infer_transient_argument_provenance(functions)[work.function_id]

    residual_slice = slice_function_residuals(
        work, transient_provenance=provenance
    ).slices[0]

    assert residual_slice.out_of_scope_effects == ()
    assert any(item.evidence.value == "NAME_INFERRED" for item in residual_slice.residuals)
