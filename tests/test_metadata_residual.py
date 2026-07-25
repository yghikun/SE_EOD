from src.metadata_residual import (
    EffectEvidence,
    FailureDomainKind,
    FailureDomainProof,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    PerCpuSlotRelation,
    ReportKind,
    ResidualClassification,
    ResidualSlice,
    ResidualState,
    SourceSite,
    residual_report,
)


def test_percpu_slot_relation_is_serialized_with_effect():
    loop_site = SourceSite("fs/xfs/xfs_super.c", 10, "for_each_possible_cpu(cpu)")
    accessor_site = SourceSite(
        "fs/xfs/xfs_super.c",
        11,
        "gc = per_cpu_ptr(mp->inodegc, cpu)",
    )
    relation = PerCpuSlotRelation(
        base_root="arg0->inodegc",
        slot_local="gc",
        index_local="cpu",
        loop_site=loop_site,
        accessor_site=accessor_site,
        source_identity="fs/xfs/xfs_super.c:10:gc",
    )
    effect = MetadataEffect(
        root="PER_CPU_SLOT(arg0->inodegc)->work",
        key="INIT_DELAYED_WORK",
        plane=MetadataPlane.STRUCTURAL,
        delta=MetadataDelta.CLOSE,
        value="inodegc_worker",
        site=accessor_site,
        percpu_slot_relation=relation,
    )

    assert effect.to_dict()["percpu_slot_relation"] == {
        "base_root": "arg0->inodegc",
        "slot_local": "gc",
        "index_local": "cpu",
        "loop_site": loop_site.to_dict(),
        "accessor_site": accessor_site.to_dict(),
        "source_identity": "fs/xfs/xfs_super.c:10:gc",
    }


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
    assert report.classification is ResidualClassification.FUNCTION_BOUNDARY_RESIDUAL
    assert report.confidence == "candidate"
    assert report.to_dict()["classification"] == "FUNCTION_BOUNDARY_RESIDUAL"
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
        residuals=(effect,),
        state=ResidualState.UNKNOWN,
    )

    report = residual_report(
        function="xfs_example",
        residual_slice=residual_slice,
        scope_rationale="helper summary missing",
    )

    assert report.kind is ReportKind.METADATA_RESIDUAL_UNKNOWN
    assert report.classification is ResidualClassification.METADATA_RESIDUAL_UNKNOWN
    assert report.confidence == "review"


def test_unknown_without_residual_is_not_a_finding():
    site = SourceSite("fs/xfs/example.c", 10, "unknown_helper(tp)")
    residual_slice = ResidualSlice(
        failure_site=site,
        reaching_effects=(),
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

    assert report.kind is ReportKind.OUT_OF_SCOPE
    assert report.classification is ResidualClassification.OUT_OF_SCOPE


def test_name_inferred_residual_is_review_not_candidate():
    site = SourceSite("fs/btrfs/example.c", 10, "btrfs_reserve_space(root)")
    effect = MetadataEffect(
        root="root",
        key="btrfs_reserve_space",
        plane=MetadataPlane.ACCOUNTING,
        delta=MetadataDelta.RESERVE,
        value="",
        site=site,
        evidence=EffectEvidence.NAME_INFERRED,
    )
    residual_slice = ResidualSlice(
        failure_site=site,
        reaching_effects=(effect,),
        cancellations=(),
        protections=(),
        residuals=(effect,),
        state=ResidualState.EXPOSED,
    )

    report = residual_report(
        function="work",
        residual_slice=residual_slice,
        scope_rationale="name-derived accounting hypothesis",
    )

    assert report.kind is ReportKind.METADATA_RESIDUAL_REVIEW
    assert (
        report.classification
        is ResidualClassification.FUNCTION_BOUNDARY_RESIDUAL_REVIEW
    )
    assert report.confidence == "review"


def test_exposed_report_ignores_contained_effect_when_selecting_review_kind():
    site = SourceSite("fs/btrfs/example.c", 10, "ret = fail_metadata()")
    transaction_effect = MetadataEffect(
        root="trans",
        key="bytes_reserved",
        plane=MetadataPlane.ACCOUNTING,
        delta=MetadataDelta.INC,
        value="nr",
        site=site,
    )
    inferred_effect = MetadataEffect(
        root="root",
        key="btrfs_update_cache",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.SET,
        value="",
        site=site,
        evidence=EffectEvidence.NAME_INFERRED,
    )
    residual_slice = ResidualSlice(
        failure_site=site,
        reaching_effects=(transaction_effect, inferred_effect),
        cancellations=(),
        protections=(),
        residuals=(transaction_effect, inferred_effect),
        state=ResidualState.EXPOSED,
        containment_proofs=(
            FailureDomainProof(
                kind=FailureDomainKind.TRANSACTION_ABORT,
                site=site,
                owner="trans",
                covered_effects=(transaction_effect,),
            ),
        ),
    )

    report = residual_report(
        function="work",
        residual_slice=residual_slice,
        scope_rationale="mixed effect-scoped containment",
    )

    assert report.kind is ReportKind.METADATA_RESIDUAL_REVIEW
    assert (
        report.classification
        is ResidualClassification.FUNCTION_BOUNDARY_RESIDUAL_REVIEW
    )
