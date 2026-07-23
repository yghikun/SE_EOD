from src.metadata_residual import (
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    ReportKind,
    ResidualSlice,
    ResidualState,
    SourceSite,
    residual_report,
)


def test_exposed_residual_becomes_candidate_report():
    opened = SourceSite("fs/btrfs/volumes.c", 100, "list_add(&device->post_commit_list, ...)")
    failure = SourceSite("fs/btrfs/volumes.c", 120, "btrfs_create_chunk(...)")
    effect = MetadataEffect(
        root="transaction",
        key="device",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.ADD,
        value="device",
        site=opened,
    )
    residual_slice = ResidualSlice(
        failure_site=failure,
        reaching_effects=(effect,),
        cancellations=(),
        protections=(),
        residuals=(effect,),
        state=ResidualState.EXPOSED,
    )

    report = residual_report(
        function="btrfs_init_new_device",
        residual_slice=residual_slice,
        scope_rationale="transaction update list is recovery-visible metadata state",
    )

    assert report.kind is ReportKind.UNCLOSED_METADATA_RESIDUAL
    assert report.confidence == "candidate"
    assert report.to_dict()["residual_slice"]["residuals"][0]["plane"] == "RECOVERY"


def test_unknown_residual_stays_review_only():
    site = SourceSite("fs/xfs/example.c", 10, "unknown_helper(tp)")
    effect = MetadataEffect(
        root="transaction",
        key="unknown",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.UNKNOWN,
        value="unknown",
        site=site,
    )
    residual_slice = ResidualSlice(
        failure_site=site,
        reaching_effects=(effect,),
        cancellations=(),
        protections=(),
        residuals=(),
        state=ResidualState.UNKNOWN,
    )

    report = residual_report(
        function="xfs_example",
        residual_slice=residual_slice,
        scope_rationale="helper summary missing",
    )

    assert report.kind is ReportKind.METADATA_RESIDUAL_UNKNOWN
    assert report.confidence == "review"
