from pathlib import Path

from src.function_extractor import extract_functions
from src.parser import parse_c_file
from src.residual_analyzer import analyze_functions


def _analyses(tmp_path: Path, source: str):
    path = tmp_path / "known_candidates.c"
    path.write_text(source, encoding="utf-8")
    functions = extract_functions(parse_c_file(path))
    return {item.function: item for item in analyze_functions(functions)}


def test_btrfs_precision_work_keeps_known_live_owner_failures_visible(tmp_path: Path):
    analyses = _analyses(
        tmp_path,
        """
int btrfs_recover_relocation(struct root *fs_root, struct root *reloc_root)
{
    int ret;

    fs_root->reloc_root = reloc_root;
    ret = fail_recovery_commit();
    if (ret)
        return ret;
    return 0;
}

int btrfs_init_new_device(struct fs_info *fs_info,
                          struct trans *trans,
                          struct device *device)
{
    int ret;

    list_add(&device->post_commit_list, &trans->dev_update_list);
    list_add(&device->dev_list, &fs_info->fs_devices->devices);
    fs_info->fs_devices->num_devices++;
    fs_info->fs_devices->latest_dev = device;
    ret = btrfs_commit_transaction(trans);
    if (ret)
        return ret;
    return 0;
}

int btrfs_reconfigure(struct fs_info *fs_info)
{
    int ret;

    set_bit(BTRFS_FS_STATE_REMOUNTING, &fs_info->fs_state);
    ret = validate_features();
    if (ret)
        return ret;
    clear_bit(BTRFS_FS_STATE_REMOUNTING, &fs_info->fs_state);
    return 0;
}

int btrfs_dev_replace_start(struct fs_info *fs_info, struct device *device)
{
    int ret;

    list_add(&device->dev_list, &fs_info->fs_devices->devices);
    fs_info->fs_devices->num_devices++;
    ret = mark_block_group_to_copy();
    if (ret)
        return ret;
    return 0;
}
""",
    )

    for function in (
        "btrfs_recover_relocation",
        "btrfs_init_new_device",
        "btrfs_reconfigure",
        "btrfs_dev_replace_start",
    ):
        assert analyses[function].candidates, function

    new_device_effects = {
        effect.key
        for report in analyses["btrfs_init_new_device"].candidates
        for effect in report.report.residual_slice.residuals
    }
    assert "list_membership" in new_device_effects
    assert "num_devices" in new_device_effects
    assert "latest_dev" in new_device_effects
