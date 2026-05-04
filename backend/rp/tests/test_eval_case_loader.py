from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from rp.eval.case_loader import load_case


def test_load_case_from_json(tmp_path):
    case_path = tmp_path / "setup_case.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "setup.commit_proposal.writing_contract.ready.v1",
                "title": "Writing contract ready proposal",
                "scope": "setup",
                "category": "commit_proposal",
                "runtime_target": {
                    "mode": "in_process",
                    "entrypoint": "setup_graph_runner.run_turn",
                    "graph_id": "setup_v2",
                    "stream": False,
                },
                "input": {
                    "request": {
                        "workspace_id": "workspace-case-1",
                        "model_id": "model-eval",
                        "provider_id": "provider-eval",
                        "user_prompt": "如果已经足够，请发起 review。",
                        "history": [],
                    },
                    "workspace_seed": {},
                    "env_overrides": {},
                },
                "preconditions": {},
                "expected": {
                    "deterministic_assertions": [],
                    "subjective_hooks": [],
                },
                "trace_hooks": {
                    "capture_runtime_events": True,
                    "capture_graph_debug": True,
                    "capture_workspace_before_after": True,
                },
                "repeat": {"count": 1, "stop_on_first_hard_failure": False},
                "baseline": {"compare_by": [], "baseline_tags": []},
                "metadata": {},
                "tags": ["mvp"],
            }
        ),
        encoding="utf-8",
    )

    case = load_case(case_path)

    assert case.case_id == "setup.commit_proposal.writing_contract.ready.v1"
    assert case.runtime_target.graph_id == "setup_v2"


def test_eval_diagnostics_import_does_not_eagerly_load_ragas():
    backend_root = Path(__file__).resolve().parents[2]
    script = (
        "import sys; "
        "import rp.eval.diagnostics; "
        "loaded = any(name == 'ragas' or name.startswith('ragas.') "
        "for name in sys.modules); "
        "raise SystemExit(1 if loaded else 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
