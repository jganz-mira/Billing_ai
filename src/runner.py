from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from threading import Event
from typing import Any

from pydantic import BaseModel

try:
    from .model_interface import ModelInterface, ModelResponseGopList
    from .ontology.schemas.care_path import ConditionalField, Model, ProcessingPath, Step
    from .ontology.schemas.gop_list import GopList
    from .ontology.schemas.patient import Patient
    from .ontology.schemas.physician import Physician
    from .prompts import GOP_CONSOLIDATION_PROMPT, GOP_EXTRACTION_BASE_PROMPT
    from .tools import GopLookupTool
except ImportError:
    from model_interface import ModelInterface, ModelResponseGopList
    from ontology.schemas.care_path import ConditionalField, Model, ProcessingPath, Step
    from ontology.schemas.gop_list import GopList
    from ontology.schemas.patient import Patient
    from ontology.schemas.physician import Physician
    from prompts import GOP_CONSOLIDATION_PROMPT, GOP_EXTRACTION_BASE_PROMPT
    from tools import GopLookupTool


class ModelRunResult(BaseModel):
    step_name: str
    expert_role: str
    model_type: str
    skipped: bool = False
    output: ModelResponseGopList | None = None
    error: str | None = None


class AnalysisCancelled(RuntimeError):
    """Raised when a running analysis is cancelled by the UI."""


def run(
    *,
    patient_path: str | Path,
    physician_path: str | Path,
    visit_documentation: str,
    care_path_dir: str | Path = "src/ontology/care_paths",
    model_interface: ModelInterface | None = None,
    verbose: bool = False,
    parallel: bool = False,
    max_workers: int = 2,
    cancel_event: Event | None = None,
) -> list[ModelRunResult]:
    patient = Patient.model_validate(_load_json(patient_path))
    physician = Physician.model_validate(_load_json(physician_path))
    care_path = _care_path_for_physician(physician, care_path_dir)
    interface = model_interface or ModelInterface()

    results: list[ModelRunResult | None] = [None] * len(care_path.steps)
    runnable_steps: list[tuple[int, Step]] = []
    for index, step in enumerate(care_path.steps):
        _raise_if_cancelled(cancel_event)
        if not _condition_matches(step.condition, patient=patient, physician=physician):
            results[index] = _base_result(step, skipped=True)
            if verbose:
                print(f"Skipping {step.prompt_template} because condition was not met.\n")
            continue
        runnable_steps.append((index, step))

    if parallel and runnable_steps:
        workers = max(1, max_workers)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _run_expert_step,
                    step,
                    patient=patient,
                    physician=physician,
                    visit_documentation=visit_documentation,
                    interface=interface,
                    verbose=verbose,
                ): index
                for index, step in runnable_steps
            }
            for future in as_completed(futures):
                _raise_if_cancelled(cancel_event)
                results[futures[future]] = future.result()
    else:
        for index, step in runnable_steps:
            _raise_if_cancelled(cancel_event)
            results[index] = _run_expert_step(
                step,
                patient=patient,
                physician=physician,
                visit_documentation=visit_documentation,
                interface=interface,
                verbose=verbose,
            )

    completed_results = [result for result in results if result is not None]
    if care_path.final_step is not None:
        _raise_if_cancelled(cancel_event)
        completed_results.append(
            _run_final_step(
                care_path.final_step,
                previous_results=completed_results,
                searchable_gop_paths=_searchable_gop_paths(care_path),
                patient=patient,
                physician=physician,
                visit_documentation=visit_documentation,
                interface=interface,
                verbose=verbose,
            )
        )

    return completed_results


def _raise_if_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled("Analyse wurde abgebrochen.")


def _run_expert_step(
    step: Step,
    *,
    patient: Patient,
    physician: Physician,
    visit_documentation: str,
    interface: ModelInterface,
    verbose: bool,
) -> ModelRunResult:
    try:
        if verbose:
            print(f"Running step {step.prompt_template}.\n")
        gops = _load_gops(step.knowledge_paths)
        system_prompt = GOP_EXTRACTION_BASE_PROMPT.format(
            expert_role=step.expert_role,
            task_focus=step.task_focus or "Kein spezifischer Zusatzfokus.",
        )
        output = interface.propose_gops(
            model=step.model_type,
            system_prompt=system_prompt,
            case_text=visit_documentation,
            patient=patient,
            physician=physician,
            gops=gops,
            reasoning_effort=step.reasoning_effort,
        )
        return _base_result(step, output=output)
    except Exception as exc:
        return _base_result(step, error=str(exc))


def _run_final_step(
    step: Model,
    *,
    previous_results: list[ModelRunResult],
    searchable_gop_paths: list[str],
    patient: Patient,
    physician: Physician,
    visit_documentation: str,
    interface: ModelInterface,
    verbose: bool,
) -> ModelRunResult:
    successful_outputs = [
        result.output
        for result in previous_results
        if not result.skipped and result.error is None and result.output is not None
    ]
    if not successful_outputs:
        return _base_result(step, error="No expert outputs to consolidate.")

    try:
        if verbose:
            print(f"Running final step {step.prompt_template}.\n")
        # The final step uses its knowledge_paths as a searchable GOP corpus.
        # Only GOPs proposed by expert steps are loaded into the consolidation prompt.
        selected_gops = _load_selected_gops(
            successful_outputs,
            searchable_gop_paths=searchable_gop_paths,
        )
        system_prompt = GOP_CONSOLIDATION_PROMPT.format(
            expert_role=step.expert_role,
            task_focus=step.task_focus or "Finale GOP-Liste erstellen.",
        )
        output = interface.consolidate_gops(
            model=step.model_type,
            system_prompt=system_prompt,
            case_text=visit_documentation,
            patient=patient,
            physician=physician,
            expert_outputs=successful_outputs,
            gops=selected_gops,
            reasoning_effort=step.reasoning_effort,
        )
        return _base_result(step, output=output)
    except Exception as exc:
        return _base_result(step, error=str(exc))


def _base_result(
    step: Model,
    *,
    skipped: bool = False,
    output: ModelResponseGopList | None = None,
    error: str | None = None,
) -> ModelRunResult:
    return ModelRunResult(
        step_name=step.prompt_template,
        expert_role=step.expert_role,
        model_type=step.model_type,
        skipped=skipped,
        output=output,
        error=error,
    )


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def _care_path_for_physician(
    physician: Physician,
    care_path_dir: str | Path,
) -> ProcessingPath:
    path = Path(care_path_dir) / f"{physician.discipline}.json"
    return ProcessingPath.model_validate(_load_json(path))


def _load_gops(paths: list[str]) -> GopList:
    merged = []
    for path in paths:
        gop_list = GopList.model_validate(_load_json(path))
        merged.extend(gop_list.gops)
    return GopList(gops=merged)


def _load_selected_gops(
    expert_outputs: list[ModelResponseGopList],
    *,
    searchable_gop_paths: list[str],
) -> GopList | None:
    if not searchable_gop_paths:
        return None

    codes: list[str] = []
    for output in expert_outputs:
        codes.extend(gop.code for gop in output.gops)

    if not codes:
        return None

    return GopLookupTool(searchable_gop_paths).load_gops(codes)


def _searchable_gop_paths(care_path: ProcessingPath) -> list[str]:
    # final_step.knowledge_paths defines the GOP files that may be searched
    # during consolidation. If omitted, all expert-step knowledge_paths are used.
    if care_path.final_step is not None and care_path.final_step.knowledge_paths:
        return _unique_paths(care_path.final_step.knowledge_paths)

    paths: list[str] = []
    for step in care_path.steps:
        paths.extend(step.knowledge_paths)
    return _unique_paths(paths)


def _unique_paths(paths: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _condition_matches(
    condition: ConditionalField | None,
    *,
    patient: Patient,
    physician: Physician,
) -> bool:
    if condition is None:
        return True

    sources: dict[str, BaseModel] = {
        "patient": patient,
        "physician": physician,
    }
    actual = _get_field_value(sources[condition.source], condition.field)
    expected = condition.value

    if condition.operator == "equals":
        return actual == expected
    if condition.operator == "not_equals":
        return actual != expected
    if condition.operator == "exists":
        return actual is not None
    if condition.operator == "not_exists":
        return actual is None
    if condition.operator == "contains":
        return actual is not None and expected in actual
    if condition.operator == "greater_than":
        return actual is not None and expected is not None and actual > expected
    if condition.operator == "greater_or_equal":
        return actual is not None and expected is not None and actual >= expected
    if condition.operator == "less_than":
        return actual is not None and expected is not None and actual < expected
    if condition.operator == "less_or_equal":
        return actual is not None and expected is not None and actual <= expected

    return False


def _get_field_value(source: BaseModel, field_path: str) -> Any:
    value: Any = source.model_dump()
    for part in field_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
