"""CLI for direct longform runtime seed materialization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlmodel import Session

from services.database import create_db_and_tables, get_engine

from rp.devtools.legal_longform_session_seed import (
    DEFAULT_TEMPLATE_PATH,
    LegalLongformSessionSeedError,
    LegalLongformSessionSeeder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_legal_longform_session",
        description=(
            "Directly materialize one legal longform runtime session without "
            "running setup activation."
        ),
    )
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE_PATH),
        help="JSON template path. Defaults to the bundled template.",
    )
    parser.add_argument("--story-id", required=True, help="Story id for the seed story.")
    parser.add_argument(
        "--label",
        help="Seed label stored in runtime_story_config.dev_seed.label.",
    )
    parser.add_argument(
        "--session-name",
        help="Alias of --label for human-readable local seed naming.",
    )
    parser.add_argument(
        "--replace",
        "--reset-if-exists",
        dest="replace",
        action="store_true",
        help=(
            "Replace only an existing seed with the same story_id and label. "
            "Refuses to touch non-seed sessions."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    label = args.session_name or args.label or args.story_id

    create_db_and_tables()
    with Session(get_engine()) as session:
        seeder = LegalLongformSessionSeeder(session)
        result = seeder.seed_from_template_path(
            template_path=args.template,
            story_id=args.story_id,
            label=label,
            replace=bool(args.replace),
        )

    payload = result.as_dict()
    print("seeded legal longform session")
    print(f"  session_id: {payload['session_id']}")
    print(f"  story_id: {payload['story_id']}")
    print(f"  label: {payload['label']}")
    print(f"  source_workspace_id: {payload['source_workspace_id']}")
    print(f"  active_branch_head_id: {payload['active_branch_head_id']}")
    print(
        "  active_runtime_profile_snapshot_id: "
        f"{payload['active_runtime_profile_snapshot_id']}"
    )
    print(f"  chapter_workspace_id: {payload['chapter_workspace_id']}")
    print(f"  outline_artifact_id: {payload['outline_artifact_id']}")
    print(f"  latest_turn_id: {payload['latest_turn_id']}")
    print("  frontend_session_id: " + payload["session_id"])
    print()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LegalLongformSessionSeedError as exc:
        print(f"[seed-error] {exc.code}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
