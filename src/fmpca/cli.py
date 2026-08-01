from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .analyzer import ProtocolAnalyzer
from .dsl import load_protocol
from .evaluation import run_and_write
from .frontend import analyze_source, load_binding
from .model import EvidenceEvent
from .proof import analyze_state
from .report import write_json
from .semantics import ProtocolEngine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmpca")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-protocol")
    validate.add_argument("protocol")

    events = sub.add_parser("analyze-events")
    events.add_argument("--protocol", required=True)
    events.add_argument("--events", required=True)
    events.add_argument("--out", required=True)

    source = sub.add_parser("analyze-source")
    source.add_argument("--protocol", required=True)
    source.add_argument("--binding", required=True)
    source.add_argument("--source", required=True)
    source.add_argument("--source-version", required=True)
    source.add_argument("--function", required=True)
    source.add_argument("--out", required=True)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--json-out", required=True)
    evaluate.add_argument("--markdown-out", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-protocol":
        spec = load_protocol(args.protocol)
        print(json.dumps({"protocol_id": spec.protocol_id, "sha256": spec.sha256}, indent=2))
        return 0
    if args.command == "analyze-events":
        spec = load_protocol(args.protocol)
        fixture = json.loads(Path(args.events).read_text(encoding="utf-8"))
        closure = fixture.get("closure", {})
        run = ProtocolAnalyzer(spec).run(
            (EvidenceEvent.from_dict(item) for item in fixture["events"]),
            path_model_closed=closure.get("path_model_closed", True),
            all_paths_closed=closure.get("all_paths_closed", False),
            repair_slice_closed=closure.get("repair_slice_closed", True),
            alias_closed=closure.get("alias_closed", True),
        )
        write_json(args.out, run.to_dict())
        print(run.result.value)
        return 0
    if args.command == "analyze-source":
        spec = load_protocol(args.protocol)
        binding = load_binding(args.binding)
        analysis = analyze_source(binding, args.source, args.function, args.source_version)
        state = ProtocolEngine(spec).run(analysis.events)
        state.assumptions.extend(analysis.assumptions)
        report = analyze_state(
            state,
            path_model_closed=analysis.path_model_closed,
            all_paths_closed=analysis.all_paths_closed,
            repair_slice_closed=analysis.repair_slice_closed,
        )
        value = report.to_dict()
        value["source_evidence"] = analysis.evidence
        value["binding_id"] = binding.binding_id
        write_json(args.out, value)
        print(report.result.value)
        return 0
    if args.command == "evaluate":
        summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
        print(f"{summary['passed']}/{summary['total']} cases passed")
        return 0 if summary["failed"] == 0 else 1
    return 2
