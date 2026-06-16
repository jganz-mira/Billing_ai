"""Streamlit UI for collecting billing case input and running GOP analysis."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from model_interface import ModelResponseGop, ModelResponseGopList, ValuationOutput
from ontology.documentations import DOCUMENTATION
from runner import ModelRunResult, run


TableRow = dict[str, Any]
AppRecord = dict[str, Any]


BASE_DIR: Path = Path(__file__).resolve().parent
PHYSICIAN_DIR: Path = BASE_DIR / "ontology" / "physicians"
PATIENT_DIR: Path = BASE_DIR / "ontology" / "patients"
DEBUG_MODE: bool = any(argument in {"--debug", "debug"} for argument in sys.argv)

# UI labels are intentionally kept close to the app layer. The ontology files
# use stable machine-readable identifiers, while Streamlit should present
# German wording that matches the target workflow.
MEDICAL_DISCIPLINE_LABELS: dict[str, str] = {
    "general_care": "Hausärztliche Versorgung",
}
CONTACT_TYPE_LABELS: dict[str, str] = {
    "personal_contact": "Persönlicher Kontakt",
    "telephone_contact": "Telefonischer Kontakt",
    "home_visit": "Hausbesuch",
    "non_physician_assistant_contact": "Kontakt mit nichtärztlicher Praxisassistenz",
}
CONTACT_LABEL_TO_VALUE: dict[str, str] = {
    label: value for value, label in CONTACT_TYPE_LABELS.items()
}
PATIENT_FIELD_LABELS: dict[str, str] = {
    "age": "Alter",
    "contact_type": "Kontakt Typ",
    "last_contact_date": "Datum des letzten Kontaktes",
    "chronic_condition": "Chroniker Status",
    "palliative_care": "Palliativ Patient",
    "geriatric_patient": "Geriatrischer Patient",
}


def load_json(path: Path) -> dict[str, Any]:
    """Load a UTF-8 encoded JSON object from disk."""
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@st.cache_data
def load_physicians() -> list[AppRecord]:
    """Load physician ontology records and attach display metadata for the UI."""
    physicians: list[AppRecord] = []
    for path in sorted(PHYSICIAN_DIR.glob("*.json")):
        data = load_json(path)
        discipline = data.get("discipline", path.stem)
        physicians.append(
            {
                "label": MEDICAL_DISCIPLINE_LABELS.get(discipline, discipline),
                "discipline": discipline,
                "path": str(path),
                "data": data,
            }
        )
    return physicians


@st.cache_data
def load_patients() -> list[AppRecord]:
    """Load predefined patient records from the ontology directory."""
    patients: list[AppRecord] = []
    for path in sorted(PATIENT_DIR.glob("*.json")):
        patients.append(
            {
                "label": path.stem,
                "path": str(path),
                "data": load_json(path),
            }
        )
    return patients


def patient_table(patient: AppRecord) -> list[TableRow]:
    """Convert a patient app record into rows suitable for st.dataframe."""
    return [
        {
            "Feld": PATIENT_FIELD_LABELS.get(key, key),
            "Wert": format_patient_value(key, value),
        }
        for key, value in patient["data"].items()
    ]


def format_patient_value(key: str, value: Any) -> str:
    """Format raw patient field values for display in the German UI."""
    if key == "contact_type":
        return CONTACT_TYPE_LABELS.get(str(value), str(value))
    if key == "last_contact_date":
        return format_german_date(str(value))
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    return str(value)


def format_german_date(value: str) -> str:
    """Format an ISO date string as DD.MM.YYYY, preserving invalid input."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return value


def yes_no_radio(label: str, key: str, value: bool = False) -> bool:
    """Render a German yes/no radio input and return the selected boolean."""
    options: list[str] = ["Ja", "Nein"]
    index: int = 0 if value else 1
    return (
        st.radio(label, options=options, index=index, horizontal=True, key=key)
        == "Ja"
    )


def clear_visit_documentation() -> None:
    """Reset the editable visit documentation in Streamlit session state."""
    st.session_state.visit_documentation = ""


def dump_model(value: Any) -> Any:
    """Return a serializable representation for pydantic models and plain values."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def format_euro(value: Any) -> str:
    """Format a numeric euro amount for the German UI."""
    if value is None:
        return ""
    if isinstance(value, int | float):
        return f"{value:.2f} EUR"
    return str(value)


def format_points(value: Any) -> str:
    """Format a numeric point value for the German UI."""
    if value is None:
        return ""
    if isinstance(value, int | float):
        return f"{value:g} Punkte"
    return str(value)


def valuation_values(value: Any) -> tuple[float, int]:
    """Extract numeric euro and point values from patient-specific valuation data."""
    if value is None:
        return 0.0, 0

    data = dump_model(value)
    if not isinstance(data, dict):
        return 0.0, 0

    euro = data.get("valuation_in_euro")
    points = data.get("valuation_in_points")
    return (
        float(euro) if isinstance(euro, int | float) else 0.0,
        int(points) if isinstance(points, int | float) else 0,
    )


def format_valuation(value: Any) -> tuple[str, str]:
    """Split patient-specific GOP valuation data into EUR and points columns."""
    if value is None:
        return "", ""

    data = dump_model(value)
    if not isinstance(data, dict):
        return str(data), ""

    return (
        format_euro(data.get("valuation_in_euro")),
        format_points(data.get("valuation_in_points")),
    )


def result_rows(
    results: list[ModelRunResult],
    *,
    final_only: bool = False,
) -> list[TableRow]:
    """Flatten runner results into display rows with one row per proposed GOP."""
    rows: list[TableRow] = []
    for result in results:
        if final_only and result.step_name != "gop_consolidation":
            continue

        if result.error is not None:
            rows.append(
                {
                    "GOP": "",
                    "Titel": "",
                    "Betrag": "",
                    "Punkte": "",
                    "Wahrscheinlichkeit": "",
                    "Begründung": result.error,
                }
            )
            continue

        output = result.output
        if result.skipped or output is None or not output.gops:
            continue

        for gop in output.gops:
            valuation_euro_value, valuation_points_value = valuation_values(
                gop.valuation
            )
            valuation_eur, valuation_points = format_valuation(gop.valuation)
            rows.append(
                {
                    "Auswahl": True,
                    "GOP": gop.code,
                    "Titel": gop.title,
                    "Betrag": valuation_eur,
                    "Punkte": valuation_points,
                    "Wahrscheinlichkeit": f"{gop.propability:.0%}",
                    "Begründung": gop.rationale,
                    "_betrag_value": valuation_euro_value,
                    "_punkte_value": valuation_points_value,
                }
            )
    return rows


def table_records(value: Any) -> list[TableRow]:
    """Return table rows from Streamlit table outputs regardless of container type."""
    if hasattr(value, "to_dict"):
        return value.to_dict("records")
    return list(value)


def debug_gop(
    *,
    code: str,
    title: str,
    euro: float | None,
    points: int | None,
    probability: float,
    rationale: str,
) -> ModelResponseGop:
    """Create a model-shaped GOP response for table debugging."""
    valuation = None
    if euro is not None and points is not None:
        valuation = ValuationOutput(
            valuation_in_euro=euro,
            valuation_in_points=points,
        )

    return ModelResponseGop(
        code=code,
        title=title,
        valuation=valuation,
        propability=probability,
        rationale=rationale,
    )


def debug_analysis_results() -> list[ModelRunResult]:
    """Return deterministic runner-shaped outputs without calling an LLM."""
    expert_output = ModelResponseGopList(
        gops=[
            debug_gop(
                code="03321",
                title="Belastungs-Elektrokardiographie (Belastungs-EKG)",
                euro=25.23,
                points=198,
                probability=0.91,
                rationale=(
                    "Dummy: Belastungs-EKG wurde in der Dokumentation als "
                    "durchgeführt angenommen."
                ),
            ),
            debug_gop(
                code="03324",
                title="Langzeit-Blutdruckmessung",
                euro=7.26,
                points=57,
                probability=0.74,
                rationale=(
                    "Dummy: Langzeit-Blutdruckmessung mit Auswertung wurde "
                    "als abrechnungsrelevant angenommen."
                ),
            ),
            debug_gop(
                code="03330",
                title="Spirographische Untersuchung",
                euro=6.75,
                points=53,
                probability=0.66,
                rationale=(
                    "Dummy: Spirographische Untersuchung wurde passend zum "
                    "Falltext simuliert."
                ),
            ),
        ]
    )
    final_output = ModelResponseGopList(
        gops=[
            debug_gop(
                code="03321",
                title="Belastungs-Elektrokardiographie (Belastungs-EKG)",
                euro=25.23,
                points=198,
                probability=0.93,
                rationale=(
                    "Dummy final: Höchste Passung, da die Leistung eindeutig "
                    "dokumentiert simuliert wurde."
                ),
            ),
            debug_gop(
                code="03324",
                title="Langzeit-Blutdruckmessung",
                euro=7.26,
                points=57,
                probability=0.81,
                rationale=(
                    "Dummy final: In die konsolidierte Liste übernommen, um "
                    "Betrag- und Punktespalten zu prüfen."
                ),
            ),
        ]
    )

    return [
        ModelRunResult(
            step_name="experte_besondere_hausarztliche_leistungen",
            expert_role="Debug-Experte fuer besondere hausaerztliche Leistungen",
            model_type="debug",
            output=expert_output,
        ),
        ModelRunResult(
            step_name="experte_palliative_hausarztliche_leistungen",
            expert_role="Debug-Experte fuer palliative Leistungen",
            model_type="debug",
            skipped=True,
        ),
        ModelRunResult(
            step_name="gop_consolidation",
            expert_role="Debug-Konsolidierer fuer GOP-Abrechnungsvorschlaege",
            model_type="debug",
            output=final_output,
        ),
    ]


def write_temp_patient(patient: AppRecord) -> Path:
    """Persist a manually entered patient as JSON for the file-based runner API."""
    path = Path(tempfile.gettempdir()) / "billing_ai_streamlit_patient.json"
    path.write_text(
        json.dumps(patient["data"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def render_analysis_results(analysis_results: list[ModelRunResult]) -> None:
    """Render final and detailed analysis tables for runner-shaped results."""
    rows: list[TableRow] = result_rows(analysis_results)
    errors: list[ModelRunResult] = [
        result for result in analysis_results if result.error is not None
    ]
    successful_gops: list[TableRow] = result_rows(analysis_results, final_only=True)

    if errors:
        st.warning(
            f"{len(errors)} Analyseschritt(e) wurden mit Fehler beendet. "
            "Details stehen in der Ergebnistabelle."
        )
    else:
        st.success("Analyse abgeschlossen.")

    st.subheader("Finale GOP-Vorschläge")
    if successful_gops:
        editor_key = f"final_gop_selection_{st.session_state.get('analysis_run_id', 0)}"
        selected_gops = st.data_editor(
            successful_gops,
            hide_index=True,
            width="stretch",
            disabled=[
                "GOP",
                "Titel",
                "Betrag",
                "Punkte",
                "Wahrscheinlichkeit",
                "Begründung",
            ],
            column_config={
                "Auswahl": st.column_config.CheckboxColumn(
                    "Auswahl",
                    default=True,
                ),
                "_betrag_value": None,
                "_punkte_value": None,
            },
            key=editor_key,
        )
        selected_records = table_records(selected_gops)
        selected_rows = [
            row for row in selected_records if row.get("Auswahl") is True
        ]
        total_euro = sum(float(row.get("_betrag_value", 0.0)) for row in selected_rows)
        total_points = sum(int(row.get("_punkte_value", 0)) for row in selected_rows)

        col_euro, col_points = st.columns(2)
        col_euro.metric("Summe Betrag", format_euro(total_euro))
        col_points.metric("Summe Punkte", format_points(total_points))
    else:
        st.info("Die Analyse hat keine finalen GOP-Vorschläge erzeugt.")

    with st.expander("Alle Analyseschritte", expanded=False):
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Auswahl": None,
                "_betrag_value": None,
                "_punkte_value": None,
            },
        )


st.set_page_config(page_title="Abrechnungs Assistent", page_icon=":clipboard:")
st.title("Abrechnungs Assistent")

physicians: list[AppRecord] = load_physicians()
patients: list[AppRecord] = load_patients()
documentation_ids: list[str] = sorted(DOCUMENTATION)

# Streamlit reruns the script on every interaction. Session state keeps the
# selected documentation and edited visit text stable across those reruns.
if "selected_documentation_id" not in st.session_state and documentation_ids:
    st.session_state.selected_documentation_id = documentation_ids[0]
if "previous_documentation_id" not in st.session_state and documentation_ids:
    st.session_state.previous_documentation_id = documentation_ids[0]
if "visit_documentation" not in st.session_state and documentation_ids:
    st.session_state.visit_documentation = DOCUMENTATION[documentation_ids[0]]

if not physicians:
    st.error("Keine medizinischen Fachrichtungen gefunden.")
    st.stop()

if not patients:
    st.error("Keine Patienteninformationen gefunden.")
    st.stop()

if not documentation_ids:
    st.error("Keine Besuchsdokumentationen gefunden.")
    st.stop()

with st.expander("Medizinische Fachrichtung", expanded=True):
    selected_physician_label: str = st.radio(
        "Medizinische Fachrichtung",
        options=[physician["label"] for physician in physicians],
        label_visibility="collapsed",
    )
    selected_physician: AppRecord = next(
        physician
        for physician in physicians
        if physician["label"] == selected_physician_label
    )

with st.expander("Informationen über den Patienten", expanded=True):
    patient_mode: str = st.radio(
        "Patient",
        options=["Vorhandenen Patienten auswählen", "Eigenen Patienten eingeben"],
        horizontal=True,
    )

    if patient_mode == "Vorhandenen Patienten auswählen":
        selected_patient_label: str = st.selectbox(
            "Vorhandener Patient",
            options=[patient["label"] for patient in patients],
        )
        selected_patient: AppRecord = next(
            patient for patient in patients if patient["label"] == selected_patient_label
        )
    else:
        contact_label: str = st.selectbox(
            "Kontakt Typ",
            options=list(CONTACT_LABEL_TO_VALUE),
            key="custom_contact_type",
        )
        # Manual patient input mirrors the patient ontology schema. Keeping the
        # shape identical lets the existing runner validate it without a
        # separate UI-specific conversion layer.
        selected_patient = {
            "label": "Eigener Patient",
            "path": None,
            "data": {
                "age": st.number_input(
                    "Alter",
                    min_value=0,
                    max_value=130,
                    value=50,
                    step=1,
                    key="custom_age",
                ),
                "contact_type": CONTACT_LABEL_TO_VALUE[contact_label],
                "last_contact_date": st.date_input(
                    "Datum des letzten Kontaktes",
                    value=date.today(),
                    format="DD.MM.YYYY",
                    key="custom_last_contact_date",
                ).isoformat(),
                "chronic_condition": yes_no_radio(
                    "Chroniker Status",
                    key="custom_chronic_condition",
                ),
                "palliative_care": yes_no_radio(
                    "Palliativ Patient",
                    key="custom_palliative_care",
                ),
                "geriatric_patient": yes_no_radio(
                    "Geriatrischer Patient",
                    key="custom_geriatric_patient",
                ),
            },
        }

    st.dataframe(
        patient_table(selected_patient),
        hide_index=True,
        width="stretch",
    )

with st.expander("Dokumentation des Patienten Besuches", expanded=True):
    selected_documentation_id: str = st.radio(
        "Dokumentation",
        options=documentation_ids,
        format_func=str,
        key="selected_documentation_id",
    )

    # Choosing a different sample documentation replaces the editable text once.
    # User edits are then preserved until another sample is selected or the
    # custom-documentation button clears the field.
    if selected_documentation_id != st.session_state.previous_documentation_id:
        st.session_state.visit_documentation = DOCUMENTATION[selected_documentation_id]
        st.session_state.previous_documentation_id = selected_documentation_id

    st.text_area(
        "Dokumentation",
        key="visit_documentation",
        height=320,
    )

    st.button(
        "Eigene Dokumentation eingeben",
        on_click=clear_visit_documentation,
    )

analyze_clicked = st.button("Analyze", type="primary")
debug_analyze_clicked = False
if DEBUG_MODE:
    debug_analyze_clicked = st.button("Debugging Analyze")

if analyze_clicked or debug_analyze_clicked:
    if analyze_clicked and not st.session_state.visit_documentation.strip():
        st.warning("Bitte zuerst eine Besuchsdokumentation eingeben.")
        st.stop()

    if debug_analyze_clicked:
        analysis_results = debug_analysis_results()
    else:
        patient_path: str | Path | None = selected_patient["path"]
        if patient_path is None:
            patient_path = write_temp_patient(selected_patient)

        # runner.run owns the domain workflow: it loads ontology files, evaluates
        # conditional care-path steps, calls the model interface, and consolidates
        # expert outputs. The app only prepares inputs and renders the result.
        with st.spinner("Analyse läuft..."):
            try:
                analysis_results = run(
                    patient_path=patient_path,
                    physician_path=selected_physician["path"],
                    visit_documentation=st.session_state.visit_documentation,
                    care_path_dir=BASE_DIR / "ontology" / "care_paths",
                    parallel=True,
                    max_workers=3,
                )
            except Exception as exc:
                st.error(f"Analyse fehlgeschlagen: {exc}")
                st.stop()

    st.session_state.analysis_results = analysis_results
    st.session_state.analysis_run_id = st.session_state.get("analysis_run_id", 0) + 1

if "analysis_results" in st.session_state:
    render_analysis_results(st.session_state.analysis_results)
