from pathlib import Path

from src.function_extractor import extract_functions
from src.function_summary import (
    SummarySource,
    apply_same_file_summary,
    build_function_summary,
    build_project_summaries,
    build_same_file_summaries,
    instantiate_summary,
)
from src.metadata_residual import MetadataDelta, MetadataPlane
from src.parser import parse_c_file


def _functions(tmp_path: Path, source: str):
    path = tmp_path / "summary.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))


def test_charge_inode_summary_opens_parameterized_accounting_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static void charge_inode(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.function_name == "charge_inode"
    assert summary.parameters == ("inode", "nr")
    assert summary.source is SummarySource.AUTO_LOCAL
    assert summary.cancels == ()
    assert len(summary.opens) == 1
    effect = summary.opens[0]
    assert (effect.root, effect.key, effect.plane, effect.delta, effect.value) == (
        "arg0",
        "i_blocks",
        MetadataPlane.ACCOUNTING,
        MetadataDelta.INC,
        "arg1",
    )


def test_uncharge_inode_summary_cancels_parameterized_accounting_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static void uncharge_inode(struct inode *inode, long nr)
{
    inode->i_blocks -= nr;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.opens == ()
    assert len(summary.cancels) == 1
    effect = summary.cancels[0]
    assert (effect.root, effect.key, effect.delta, effect.value) == (
        "arg0",
        "i_blocks",
        MetadataDelta.DEC,
        "arg1",
    )


def test_summary_canonicalizes_parameter_bound_local_alias(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static void bump_devices(struct fs_info *fs_info)
{
    struct fs_devices *fs_devices = fs_info->fs_devices;

    fs_devices->num_devices++;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert len(summary.opens) == 1
    effect = summary.opens[0]
    assert (effect.root, effect.key, effect.delta, effect.value) == (
        "arg0->fs_devices",
        "num_devices",
        MetadataDelta.INC,
        "1",
    )
    assert summary.unknown_escape is False


def test_summary_drops_unbound_callee_local_identity(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static void attach_private_device(struct fs_info *fs_info)
{
    struct fs_devices *old_devices;

    list_add(&old_devices->fs_list, &fs_uuids);
}
""",
    )[0]

    summary = build_function_summary(function)
    application = instantiate_summary(summary, "attach_private_device(fs_info)")

    assert summary.opens == ()
    assert summary.unknown_escape is True
    assert summary.unknown_causes == ("unbound_callee_local_identity",)
    assert application.unknown
    assert application.opens == ()


def test_summary_binds_fresh_local_after_list_ownership_transfer(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int attach_device(struct fs_devices *fs_devices)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    if (!device)
        return -ENOMEM;
    device->ready = 1;
    list_add(&device->dev_list, &fs_devices->devices);
    return 0;
}
""",
    )[0]

    summary = build_function_summary(function)
    application = instantiate_summary(summary, "attach_device(fs_devices)")

    assert summary.unknown_escape is False
    assert summary.fresh_identities == ("__fresh0__",)
    assert summary.ownership_transfer_roots == ("arg0->devices",)
    assert not application.unknown
    assert len(application.opens) == 2
    assert application.opens[0].root == "__fresh_attach_device_0__"
    assert application.opens[1].root == "fs_devices->devices"
    assert application.opens[1].value == "__fresh_attach_device_0__->dev_list"


def test_summary_binds_fresh_local_to_caller_owned_field(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int install_device(struct fs_info *fs_info)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    if (!device)
        return -ENOMEM;
    device->ready = 1;
    fs_info->device = device;
    return 0;
}
""",
    )[0]

    summary = build_function_summary(function)
    application = instantiate_summary(summary, "install_device(fs_info)")

    assert summary.unknown_escape is False
    assert summary.fresh_identities == ()
    assert [(effect.root, effect.key, effect.value) for effect in application.opens] == [
        ("fs_info->device", "ready", "1"),
        ("fs_info", "device", "fs_info->device"),
    ]


def test_summary_keeps_untransferred_allocated_local_unknown(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int prepare_private_device(struct fs_info *fs_info)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    if (!device)
        return -ENOMEM;
    device->ready = fs_info->ready;
    return 0;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.opens == ()
    assert summary.fresh_identities == ()
    assert summary.unknown_causes == ("unbound_callee_local_identity",)


def test_same_file_fresh_return_propagates_to_transfer_summary(tmp_path: Path):
    allocator, installer = _functions(
        tmp_path,
        """
static struct device *alloc_device(void)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    return device;
}

static int install_device(struct fs_devices *fs_devices)
{
    struct device *device = alloc_device();

    if (!device)
        return -ENOMEM;
    list_add(&device->dev_list, &fs_devices->devices);
    return 0;
}
""",
    )

    summaries = build_same_file_summaries((allocator, installer))
    allocator_summary = summaries["alloc_device"]
    installer_summary = summaries["install_device"]

    assert allocator_summary.returns_fresh_identity is True
    assert installer_summary.has_ownership_transfer is True
    assert installer_summary.fresh_identities == ("__fresh0__",)
    assert installer_summary.unknown_causes == ()


def test_summary_binds_fresh_local_to_output_parameter(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int init_device(struct fs_devices *fs_devices, struct device **device_out)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    if (!device)
        return -ENOMEM;
    device->ready = 1;
    list_add(&device->dev_list, &fs_devices->devices);
    fs_devices->num_devices++;
    *device_out = device;
    return 0;
}
""",
    )[0]

    summary = build_function_summary(function)
    application = instantiate_summary(
        summary,
        "init_device(fs_devices, &tgt_device)",
    )

    assert summary.output_identities == ("__output1__",)
    assert summary.fresh_identities == ()
    assert summary.failure_effects_complete is True
    assert application.error_opens == ()
    assert not application.unknown
    assert any(effect.root == "tgt_device" for effect in application.opens)
    assert any(effect.value == "tgt_device->dev_list" for effect in application.opens)


def test_project_summaries_propagate_unique_external_fresh_return(tmp_path: Path):
    allocator = _functions(
        tmp_path,
        """
struct device *alloc_device(void)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    return device;
}
""",
    )[0]
    installer = _functions(
        tmp_path,
        """
int install_device(struct fs_devices *fs_devices)
{
    struct device *device = alloc_device();

    if (!device)
        return -ENOMEM;
    list_add(&device->dev_list, &fs_devices->devices);
    return 0;
}
""",
    )[0]

    summaries = build_project_summaries((allocator, installer))

    assert summaries["alloc_device"].returns_fresh_identity is True
    assert summaries["install_device"].has_ownership_transfer is True
    assert summaries["install_device"].unknown_causes == ()


def test_summary_tracks_all_pointer_symbols_in_multi_declaration(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int insert_node(struct tree *tree)
{
    struct node *entry, *node;

    node = kzalloc(sizeof(*node), GFP_KERNEL);
    if (!node)
        return -ENOMEM;
    rb_link_node(&node->rb, entry, &tree->root.rb_node);
    return 0;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.opens == ()
    assert summary.unknown_causes == ("unbound_callee_local_identity",)


def test_summary_binds_returned_local_identity_to_call_lvalue(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static struct dev *make_dev(void)
{
    struct dev *dev;

    dev->ready = 1;
    return dev;
}
""",
    )[0]

    summary = build_function_summary(function)
    unresolved = instantiate_summary(summary, "make_dev()")
    application = instantiate_summary(summary, "make_dev()", return_lvalue="dev")

    assert summary.returns == ("__return__",)
    assert unresolved.unknown
    assert unresolved.unresolved_identities == ("__return__",)
    assert not application.unknown
    assert application.returns == ("dev",)
    assert (application.opens[0].root, application.opens[0].key) == ("dev", "ready")


def test_summary_marks_unresolved_metadata_helper_as_unknown_escape(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static struct dev *open_seed(void)
{
    struct dev *dev;

    dev->ready = 1;
    clone_fs_devices(dev);
    return dev;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.unknown_escape is True
    assert summary.unknown_causes == (
        "return_bound_unresolved_helper: clone_fs_devices",
    )


def test_scalar_status_return_does_not_create_return_bound_unknown(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int update_status(struct trans *trans)
{
    int ret = 0;

    trans->transaction_status = ret;
    btrfs_root_id(trans);
    return ret;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.returns == ("ret",)
    assert summary.unknown_escape is False
    assert summary.unknown_causes == ()
    assert summary.opens[0].value == "ret"


def test_call_site_instantiates_summary_arguments(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static void charge_inode(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}
""",
    )[0]
    summary = build_function_summary(function)

    application = instantiate_summary(summary, "charge_inode(inode, nr)")

    assert not application.unknown
    effect = application.opens[0]
    assert (effect.root, effect.key, effect.delta, effect.value) == (
        "inode",
        "i_blocks",
        MetadataDelta.INC,
        "nr",
    )


def test_unresolved_argument_identity_becomes_unknown(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static void charge_inode(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}
""",
    )[0]
    summary = build_function_summary(function)

    application = instantiate_summary(summary, "charge_inode(inode)")

    assert application.unknown
    assert application.unresolved_identities == ("arg1",)
    assert application.opens[0].value == "arg1"


def test_same_file_summaries_include_static_helpers_and_apply_call(tmp_path: Path):
    charge, caller = _functions(
        tmp_path,
        """
static void charge_inode(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}

void caller(struct inode *inode, long nr)
{
    charge_inode(inode, nr);
}
""",
    )

    summaries = build_same_file_summaries((charge, caller))
    application = apply_same_file_summary(summaries, "charge_inode(inode, nr)")

    assert set(summaries) == {"charge_inode"}
    assert application is not None
    assert application.opens[0].root == "inode"


def test_summary_records_may_fail_and_unknown_escape(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
static int helper(struct inode *inode, long nr, void (*callback)(void *))
{
    int ret;

    inode->i_blocks += nr;
    callback(inode);
    ret = reserve_blocks();
    if (ret)
        return ret;
    return 0;
}
""",
    )[0]

    summary = build_function_summary(function)

    assert summary.may_fail is True
    assert summary.unknown_escape is True
    assert summary.unknown_causes == ("function_pointer_parameter_call: callback",)
