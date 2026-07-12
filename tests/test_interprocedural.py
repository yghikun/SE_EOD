import json
from pathlib import Path

from src.error_condition import ConditionInfo
from src.function_extractor import Function
from src.function_summary import infer_function_summaries
from src.label_resolver import Statement
from src.resource_state import (
    ResourceAction,
    ResourceState,
    error_path_violation,
    join_states,
    transition,
)
from src.resource_tracker import ResourceTracker


RESOURCE_MAP = {
    "acquire_functions": {
        "kmalloc": {"resource_type": "memory", "release": ["kfree"]},
        "cache_alloc": {
            "resource_type": "cache_object",
            "release": ["cache_free"],
            "release_arg_index": 1,
        },
        "load_item": {
            "resource_type": "memory",
            "release": ["kfree"],
            "out_resource_arg": 0,
            "out_arg_requires_address": True,
        },
    }
}


def function(name: str, parameters: str, body: str) -> Function:
    return Function(
        file=Path("demo.c"),
        name=name,
        signature=f"static void {name}({parameters})",
        source=f"static void {name}({parameters}) {{ {body} }}",
        body=body,
        start_line=1,
        end_line=3,
        body_start_line=2,
    )


def test_resource_state_model_is_conservative():
    assert transition(ResourceState.UNSEEN, ResourceAction.ACQUIRE) is ResourceState.ACQUIRED
    assert transition(ResourceState.ACQUIRED, ResourceAction.RELEASE) is ResourceState.RELEASED
    assert transition(ResourceState.BORROWED, ResourceAction.RELEASE) is ResourceState.UNKNOWN
    assert join_states(ResourceState.RELEASED, ResourceState.ACQUIRED) is ResourceState.UNKNOWN
    assert join_states(ResourceState.UNSEEN, ResourceState.ACQUIRED) is ResourceState.UNKNOWN
    assert error_path_violation(ResourceState.ACQUIRED).kind == "missing_cleanup"
    assert error_path_violation(ResourceState.TRANSFERRED) is None


def test_release_summary_propagates_to_fixed_point():
    functions = [
        function("leaf_free", "void *ptr", "kfree(ptr);"),
        function("middle_free", "void *value", "leaf_free(value);"),
        function("outer_free", "void *owned", "middle_free(owned);"),
    ]

    db = infer_function_summaries(functions, RESOURCE_MAP)
    effect = db.find("outer_free").effects[0]

    assert db.converged
    assert effect.resource == "arg0"
    assert effect.action == "release"
    assert effect.resource_type == "memory"
    assert effect.evidence[0] == "outer_free calls middle_free"
    assert db.call_graph["outer_free"] == ("middle_free",)


def test_external_transfer_seed_propagates_through_local_wrapper():
    resource_map = {
        **RESOURCE_MAP,
        "interprocedural_effect_seeds": {
            "register_cleanup": {
                "resource": "arg2",
                "action": "transfer",
                "evidence": "reviewed callback ownership contract",
            }
        },
    }
    db = infer_function_summaries(
        [
            function(
                "defer_free",
                "void *callback, void *ptr",
                "register_cleanup(callback, free_item, ptr);",
            )
        ],
        resource_map,
    )

    seeded = db.find("register_cleanup")
    propagated = db.find("defer_free")
    assert seeded is not None
    assert seeded.effects[0].resource == "arg2"
    assert seeded.effects[0].action == "transfer"
    assert propagated is not None
    assert any(
        effect.resource == "arg1" and effect.action == "transfer"
        for effect in propagated.effects
    )
    assert db.call_graph["defer_free"] == ("register_cleanup",)


def test_external_transfer_seed_consumes_matching_local_resource_only():
    resource_map = {
        **RESOURCE_MAP,
        "interprocedural_effect_seeds": {
            "register_cleanup": {"resource": "arg2", "action": "transfer"}
        },
    }
    summaries = infer_function_summaries([], resource_map)
    tracker = ResourceTracker(resource_map, summaries)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("other = kmalloc(8);", 2),
        Statement("register_cleanup(callback, kfree, ptr);", 3),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(statements, 4, condition, "ret")
    assert [resource.var for resource in held] == ["other"]


def test_summary_supports_nonfirst_release_argument_and_acquire_return():
    functions = [
        function("drop_cache", "void *cache, void *item", "cache_free(cache, item);"),
        function("new_item", "void", "void *item = kmalloc(8); return item;"),
    ]

    db = infer_function_summaries(functions, RESOURCE_MAP)

    assert db.find("drop_cache").effects[0].resource == "arg1"
    assert db.find("new_item").effects[0].resource == "return"
    assert db.find("new_item").effects[0].action == "acquire"


def test_return_acquisition_propagates_through_wrapper():
    functions = [
        function("new_item", "void", "void *item = kmalloc(8); return item;"),
        function("outer_new_item", "void", "return new_item();"),
    ]

    db = infer_function_summaries(functions, RESOURCE_MAP)
    effect = db.find("outer_new_item").effects[0]

    assert effect.resource == "return"
    assert effect.action == "acquire"
    assert effect.evidence[0] == "outer_new_item returns result of new_item"


def test_recursive_call_graph_converges_without_duplicate_evidence_effects():
    functions = [
        function("cycle_a", "void *ptr", "cycle_b(ptr);"),
        function("cycle_b", "void *ptr", "kfree(ptr); cycle_a(ptr);"),
    ]

    db = infer_function_summaries(functions, RESOURCE_MAP)

    assert db.converged
    assert db.iterations < 50
    assert len(db.find("cycle_a").effects) == 1
    assert len(db.find("cycle_b").effects) == 1


def test_unknown_parameter_call_is_recorded_without_assuming_safety():
    db = infer_function_summaries(
        [function("pass_unknown", "void *ptr", "external_callback(ptr);")],
        RESOURCE_MAP,
    )

    assert db.find("pass_unknown").unresolved_calls == ["external_callback"]
    assert db.find("pass_unknown").effects == []


def test_resource_tracker_consumes_propagated_release_summary():
    summaries = infer_function_summaries(
        [
            function("leaf_free", "void *ptr", "kfree(ptr);"),
            function("wrapper_free", "void *ptr", "leaf_free(ptr);"),
        ],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("wrapper_free(ptr);", 2),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    assert tracker.held_before(statements, 3, condition, "ret") == []


def test_conditional_release_summary_does_not_suppress_held_resource():
    summaries = infer_function_summaries(
        [function("maybe_free", "void *ptr", "if (enabled) kfree(ptr);")],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("maybe_free(ptr);", 2),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(statements, 3, condition, "ret")
    assert [resource.var for resource in held] == ["ptr"]


def test_conditional_release_normalizes_parameter_and_applies_constant_flag():
    summaries = infer_function_summaries(
        [
            function(
                "maybe_free",
                "void *ptr, int release_now",
                "if (release_now) kfree(ptr);",
            )
        ],
        RESOURCE_MAP,
    )
    effect = summaries.find("maybe_free").effects[0]
    assert effect.condition == "arg1"

    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")
    released = tracker.held_before(
        [
            Statement("ptr = kmalloc(8);", 1),
            Statement("maybe_free(ptr, 1);", 2),
        ],
        3,
        condition,
        "ret",
    )
    retained = tracker.held_before(
        [
            Statement("ptr = kmalloc(8);", 1),
            Statement("maybe_free(ptr, 0);", 2),
        ],
        3,
        condition,
        "ret",
    )
    released_noncanonical_true = tracker.held_before(
        [
            Statement("ptr = kmalloc(8);", 1),
            Statement("maybe_free(ptr, 2);", 2),
        ],
        3,
        condition,
        "ret",
    )

    assert released == []
    assert released_noncanonical_true == []
    assert [resource.var for resource in retained] == ["ptr"]


def test_null_safe_release_applies_to_successfully_held_resource():
    summaries = infer_function_summaries(
        [function("safe_free", "void *ptr", "if (ptr) kfree(ptr);")],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(
        [
            Statement("ptr = kmalloc(8);", 1),
            Statement("safe_free(ptr);", 2),
        ],
        3,
        condition,
        "ret",
    )

    assert held == []


def test_conditional_effect_remaps_flag_through_wrapper():
    summaries = infer_function_summaries(
        [
            function(
                "maybe_free",
                "void *ptr, int release_now",
                "if (release_now) kfree(ptr);",
            ),
            function(
                "wrapper_free",
                "int enabled, void *value",
                "maybe_free(value, enabled);",
            ),
        ],
        RESOURCE_MAP,
    )
    effects = summaries.find("wrapper_free").effects

    assert any(
        effect.resource == "arg1"
        and effect.action == "release"
        and effect.condition == "(arg0)"
        for effect in effects
    )


def test_tracker_acquires_resource_returned_by_local_wrapper():
    summaries = infer_function_summaries(
        [function("new_item", "void", "void *item = kmalloc(8); return item;")],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    statements = [Statement("ptr = new_item();", 1)]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(statements, 2, condition, "ret")
    assert [(resource.var, resource.acquire_func) for resource in held] == [
        ("ptr", "new_item")
    ]
    assert held[0].release_functions == ["kfree"]


def test_conditional_return_acquisition_records_null_argument_condition():
    summaries = infer_function_summaries(
        [
            function(
                "maybe_new_item",
                "void **orig",
                "void *item = orig ? *orig : NULL; "
                "if (!item) item = kmalloc(8); return item;",
            )
        ],
        RESOURCE_MAP,
    )
    effect = summaries.find("maybe_new_item").effects[0]

    assert effect.resource == "return"
    assert effect.action == "acquire"
    assert effect.condition == "arg0 == NULL"


def test_conditional_return_acquisition_applies_only_for_null_argument():
    summaries = infer_function_summaries(
        [
            function(
                "maybe_new_item",
                "void **orig",
                "void *item = orig ? *orig : NULL; "
                "if (!item) item = kmalloc(8); return item;",
            )
        ],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(
        [Statement("ptr = maybe_new_item(NULL);", 1)], 2, condition, "ret"
    )
    assert [(resource.var, resource.acquire_func) for resource in held] == [
        ("ptr", "maybe_new_item")
    ]

    held = tracker.held_before(
        [Statement("ptr = maybe_new_item(&cached);", 1)], 2, condition, "ret"
    )
    assert held == []


def test_tracker_acquires_resource_from_wrapper_out_parameter():
    summaries = infer_function_summaries(
        [function("load_wrapper", "void **result", "return load_item(result);")],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    statements = [Statement("load_wrapper(&ptr);", 1)]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(statements, 2, condition, "ret")
    assert [(resource.var, resource.acquire_func) for resource in held] == [
        ("ptr", "load_wrapper")
    ]


def test_cleanup_wrapper_summary_releases_acquired_wrapper_result():
    summaries = infer_function_summaries(
        [
            function("new_item", "void", "void *item = kmalloc(8); return item;"),
            function("free_item", "void *item", "kfree(item);"),
        ],
        RESOURCE_MAP,
    )
    tracker = ResourceTracker(RESOURCE_MAP, summaries)
    statements = [Statement("ptr = new_item();", 1)]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")
    held = tracker.held_before(statements, 2, condition, "ret")

    assert tracker.missing_cleanup_candidates(held, ["free_item(ptr)"]) == []


def test_local_field_store_escapes_held_resource():
    tracker = ResourceTracker(RESOURCE_MAP)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("holder->resource = ptr;", 2),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    assert tracker.held_before(statements, 3, condition, "ret") == []


def test_local_dot_field_store_escapes_cast_held_resource():
    tracker = ResourceTracker(RESOURCE_MAP)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("holder.resource = (struct item *)ptr;", 2),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    assert tracker.held_before(statements, 3, condition, "ret") == []


def test_plain_alias_assignment_does_not_escape_held_resource():
    tracker = ResourceTracker(RESOURCE_MAP)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("alias = ptr;", 2),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(statements, 3, condition, "ret")
    assert [resource.var for resource in held] == ["ptr"]


def test_field_rhs_does_not_escape_by_tail_name_only():
    tracker = ResourceTracker(RESOURCE_MAP)
    statements = [
        Statement("ptr = kmalloc(8);", 1),
        Statement("holder->resource = other->ptr;", 2),
    ]
    condition = ConditionInfo("ret < 0", "negative_error", "ret", "high", "test")

    held = tracker.held_before(statements, 3, condition, "ret")
    assert [resource.var for resource in held] == ["ptr"]


def test_summary_serialization_preserves_propagation_evidence(tmp_path):
    db = infer_function_summaries(
        [function("leaf_free", "void *ptr", "kfree(ptr);")], RESOURCE_MAP
    )
    target = tmp_path / "summaries.json"
    db.write_json(target)
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["summaries"][0]["effects"][0]["evidence"]
