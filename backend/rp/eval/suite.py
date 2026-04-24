"""Batch execution helpers for eval suites."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from .case_loader import load_cases
from .models import EvalCase, EvalSuiteCaseResult, EvalSuiteResult
from .runner import EvalRunner


class EvalSuiteRunner:
    """Run one or more eval cases and persist report bundles."""

    def __init__(self, session: Session, *, runner: EvalRunner | None = None) -> None:
        self._runner = runner or EvalRunner(session)

    async def run_path(
        self,
        path: str | Path,
        *,
        output_dir: str | Path | None = None,
        repeat_override: int | None = None,
    ) -> EvalSuiteResult:
        return await self.run_cases(
            load_cases(path),
            output_dir=output_dir,
            repeat_override=repeat_override,
        )

    async def run_cases(
        self,
        cases: list[EvalCase],
        *,
        output_dir: str | Path | None = None,
        repeat_override: int | None = None,
    ) -> EvalSuiteResult:
        suite_id = uuid4().hex
        target_dir = Path(output_dir) if output_dir is not None else None
        if target_dir is not None:
            (target_dir / "reports").mkdir(parents=True, exist_ok=True)
            (target_dir / "replays").mkdir(parents=True, exist_ok=True)

        items: list[EvalSuiteCaseResult] = []
        pass_count = 0
        fail_count = 0
        run_count = 0

        for case in cases:
            repeat_count = max(
                1,
                int(repeat_override if repeat_override is not None else case.repeat.count),
            )
            for attempt_index in range(1, repeat_count + 1):
                run_case = (
                    _apply_repeat_identity(case=case, attempt_index=attempt_index)
                    if repeat_count > 1
                    else case
                )
                if target_dir is not None and "save_replay_dir" not in case.input.env_overrides:
                    run_case = run_case.model_copy(
                        deep=True,
                        update={
                            "input": run_case.input.model_copy(
                                deep=True,
                                update={
                                    "env_overrides": {
                                        **run_case.input.env_overrides,
                                        "save_replay_dir": str(target_dir / "replays"),
                                    }
                                },
                            )
                        },
                    )
                result = await self._runner.run_case(run_case)
                run_count += 1
                fail_total = int(result.report.get("assertion_summary", {}).get("fail", 0))
                if fail_total == 0:
                    pass_count += 1
                else:
                    fail_count += 1
                report_path = None
                if target_dir is not None:
                    report_name = (
                        f"{_safe_name(result.case.case_id)}--attempt-{attempt_index}--{result.run.run_id}.json"
                        if repeat_count > 1
                        else f"{_safe_name(result.case.case_id)}--{result.run.run_id}.json"
                    )
                    report_path = target_dir / "reports" / report_name
                    report_path.write_text(
                        json.dumps(result.report, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                items.append(
                    EvalSuiteCaseResult(
                        case_id=result.case.case_id,
                        run_id=result.run.run_id,
                        scope=result.case.scope,
                        status=result.run.status,
                        attempt_index=attempt_index,
                        replay_path=result.report.get("replay_path"),
                        report_path=report_path.as_posix() if report_path is not None else None,
                        report=result.report,
                    )
                )

        suite_result = EvalSuiteResult(
            suite_id=suite_id,
            case_count=len(cases),
            run_count=run_count,
            pass_count=pass_count,
            fail_count=fail_count,
            output_dir=target_dir.as_posix() if target_dir is not None else None,
            items=items,
        )
        if target_dir is not None:
            (target_dir / "suite-summary.json").write_text(
                json.dumps(suite_result.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return suite_result


def _safe_name(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_")


def _apply_repeat_identity(*, case: EvalCase, attempt_index: int) -> EvalCase:
    suffix = f"--repeat-{attempt_index}"
    request = dict(case.input.request)
    workspace_seed = dict(case.input.workspace_seed)

    workspace_id = request.get("workspace_id")
    if workspace_id:
        request["workspace_id"] = f"{workspace_id}{suffix}"

    story_id = workspace_seed.get("story_id")
    if story_id:
        workspace_seed["story_id"] = f"{story_id}{suffix}"

    return case.model_copy(
        deep=True,
        update={
            "input": case.input.model_copy(
                deep=True,
                update={
                    "request": request,
                    "workspace_seed": workspace_seed,
                },
            )
        },
    )
