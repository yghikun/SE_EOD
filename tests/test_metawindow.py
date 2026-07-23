from src.metawindow import (
    FailureWindow,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    ReportKind,
    SourceSite,
    WindowState,
    error_exit_report,
)


def test_exposed_window_becomes_candidate_report():
    opened = SourceSite("fs/btrfs/volumes.c", 100, "list_add(&device->post_commit_list, ...)")
    fallible = SourceSite("fs/btrfs/volumes.c", 120, "btrfs_create_chunk(...)")
    effect = MetadataEffect(
        root="transaction",
        key="device",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.ADD,
        site=opened,
    )
    window = FailureWindow(effect=effect, state=WindowState.EXPOSED, fallible_site=fallible)

    report = error_exit_report(
        function="btrfs_init_new_device",
        window=window,
        scope_rationale="transaction update list is recovery-visible metadata state",
    )

    assert report.kind is ReportKind.UNCLOSED_METADATA_FAILURE_WINDOW
    assert report.confidence == "candidate"
    assert report.to_dict()["window"]["effect"]["plane"] == "RECOVERY"


def test_unknown_window_stays_review_only():
    site = SourceSite("fs/xfs/example.c", 10, "unknown_helper(tp)")
    effect = MetadataEffect(
        root="transaction",
        key="unknown",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.UNKNOWN,
        site=site,
    )
    window = FailureWindow(effect=effect, state=WindowState.UNKNOWN, fallible_site=site)

    report = error_exit_report(
        function="xfs_example",
        window=window,
        scope_rationale="helper summary missing",
    )

    assert report.kind is ReportKind.METADATA_WINDOW_UNKNOWN
    assert report.confidence == "review"
