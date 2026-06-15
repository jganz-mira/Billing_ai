from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from datetime import date, datetime

import streamlit as st

from ontology.documentations import DOCUMENTATION


BASE_DIR = Path(__file__).resolve().parent
PHYSICIAN_DIR = BASE_DIR / "ontology" / "physicians"
PATIENT_DIR = BASE_DIR / "ontology" / "patients"
MEDICAL_DISCIPLINE_LABELS = {
    "general_care": "Hausärztliche Versorgung",
}
CONTACT_TYPE_LABELS = {
    "personal_contact": "Persönlicher Kontakt",
    "telephone_contact": "Telefonischer Kontakt",
    "home_visit": "Hausbesuch",
    "non_physician_assistant_contact": "Kontakt mit nichtärztlicher Praxisassistenz",
}
CONTACT_LABEL_TO_VALUE = {
    label: value for value, label in CONTACT_TYPE_LABELS.items()
}
PATIENT_FIELD_LABELS = {
    "age": "Alter",
    "contact_type": "Kontakt Typ",
    "last_contact_date": "Datum des letzten Kontaktes",
    "chronic_condition": "Chroniker Status",
    "palliative_care": "Palliativ Patient",
    "geriatric_patient": "Geriatrischer Patient",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@st.cache_data
def load_physicians() -> list[dict[str, Any]]:
    physicians = []
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
def load_patients() -> list[dict[str, Any]]:
    patients = []
    for path in sorted(PATIENT_DIR.glob("*.json")):
        patients.append(
            {
                "label": path.stem,
                "path": str(path),
                "data": load_json(path),
            }
        )
    return patients


def patient_table(patient: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"Feld": PATIENT_FIELD_LABELS.get(key, key), "Wert": format_patient_value(key, value)}
        for key, value in patient["data"].items()
    ]


def format_patient_value(key: str, value: Any) -> str:
    if key == "contact_type":
        return CONTACT_TYPE_LABELS.get(str(value), str(value))
    if key == "last_contact_date":
        return format_german_date(str(value))
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    return str(value)


def format_german_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return value


def yes_no_radio(label: str, key: str, value: bool = False) -> bool:
    options = ["Ja", "Nein"]
    index = 0 if value else 1
    return st.radio(label, options=options, index=index, horizontal=True, key=key) == "Ja"


def clear_visit_documentation() -> None:
    st.session_state.visit_documentation = ""


st.set_page_config(page_title="Abrechnungs Assistent", page_icon=":clipboard:")
st.title("Abrechnungs Assistent")

physicians = load_physicians()
patients = load_patients()
documentation_ids = sorted(DOCUMENTATION)

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
    selected_physician_label = st.radio(
        "Medizinische Fachrichtung",
        options=[physician["label"] for physician in physicians],
        label_visibility="collapsed",
    )
    selected_physician = next(
        physician
        for physician in physicians
        if physician["label"] == selected_physician_label
    )

with st.expander("Informationen über den Patienten", expanded=True):
    patient_mode = st.radio(
        "Patient",
        options=["Vorhandenen Patienten auswählen", "Eigenen Patienten eingeben"],
        horizontal=True,
    )

    if patient_mode == "Vorhandenen Patienten auswählen":
        selected_patient_label = st.selectbox(
            "Vorhandener Patient",
            options=[patient["label"] for patient in patients],
        )
        selected_patient = next(
            patient for patient in patients if patient["label"] == selected_patient_label
        )
    else:
        contact_label = st.selectbox(
            "Kontakt Typ",
            options=list(CONTACT_LABEL_TO_VALUE),
            key="custom_contact_type",
        )
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
    selected_documentation_id = st.radio(
        "Dokumentation",
        options=documentation_ids,
        format_func=str,
        key="selected_documentation_id",
    )

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

if st.button("Analyze", type="primary"):
    st.info(
        "Auswahl wurde übernommen. runner.py ist in dieser Version noch nicht "
        "verdrahtet."
    )
    st.write(
        {
            "medical_discipline": selected_physician["label"],
            "physician_path": selected_physician["path"],
            "patient": selected_patient["label"],
            "patient_path": selected_patient["path"],
            "documentation_id": selected_documentation_id,
        }
    )
