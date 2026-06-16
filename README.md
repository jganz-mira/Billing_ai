# Billing AI

Billing AI ist ein Streamlit-Prototyp fuer GOP-Abrechnungsvorschlaege. Die App
nimmt eine medizinische Fachrichtung, Patientendaten und eine Besuchsdokumentation
entgegen. Die eigentliche Abrechnungspipeline in `src/runner.py` fuehrt dann
mehrere fachliche Expertenschritte aus und kann deren Ergebnisse in einem finalen
GOP-Vorschlag konsolidieren.

## Setup und Start

Voraussetzungen:

- Python `>=3.12,<4.0`
- Poetry
- Fuer echte Modellaufrufe: `OPENAI_API_KEY`

Abhaengigkeiten installieren:

```bash
poetry install
```

App starten:

```bash
poetry run streamlit run src/app.py
```

Debug-Modus ohne LLM-Call starten:

```bash
poetry run streamlit run src/app.py debug
```

Im Debug-Modus ist zusaetzlich der Button `Debugging Analyze` sichtbar. Er
erzeugt deterministische Dummy-Ergebnisse im gleichen Format wie die Modelle,
damit die Ergebnistabellen und Summenberechnung ohne API-Aufruf getestet werden
koennen.

## Wichtige Projektstruktur

- `src/app.py`: Streamlit UI fuer Fachrichtung, Patient, Dokumentation und
  Ergebnisdarstellung.
- `src/runner.py`: Fuehrt Abrechnungspfade aus, prueft Bedingungen und startet
  Experten- sowie Konsolidierungsschritte.
- `src/model_interface.py`: OpenAI-Anbindung und strukturierte Modellantworten.
- `src/ontology/physicians/`: Arzt- und Fachrichtungsdaten.
- `src/ontology/patients/`: Beispielpatienten fuer die UI.
- `src/ontology/care_paths/`: Abrechnungspfade.
- `src/ontology/gops/`: GOP-Wissensdateien, die den Expertenschritten
  uebergeben werden.
- `src/ontology/schemas/`: Pydantic-Schemas fuer Pfade, GOPs, Patienten und
  Aerzte.

## Aufbau der Abrechnungspfade

Ein Abrechnungspfad ist eine JSON-Datei in `src/ontology/care_paths/`. Der
Dateiname muss zur `discipline` der ausgewaehlten Arztdatei passen. Beispiel:

- `src/ontology/physicians/general_care.json` enthaelt
  `"discipline": "general_care"`
- `src/runner.py` laedt dazu
  `src/ontology/care_paths/general_care.json`

Ein Pfad folgt dem Schema `ProcessingPath` aus
`src/ontology/schemas/care_path.py`:

- `name`: technischer Name des Abrechnungspfads.
- `steps`: Liste der Expertenschritte.
- `final_step`: optionaler finaler Schritt zur Konsolidierung aller
  erfolgreichen Expertenoutputs.

Ein einzelner Step kann diese Felder enthalten:

- `expert_role`: Rolle, die im Systemprompt verwendet wird.
- `model_type`: OpenAI-Modellname, z. B. `gpt-5-mini`.
- `prompt_template`: technischer Name des Prompt-Templates bzw. Schritts.
- `task_focus`: optionaler Fokus fuer diesen Expertenschritt.
- `knowledge_paths`: Liste repo-relativer GOP-Wissensdateien.
- `reasoning_effort`: optional, `low`, `medium` oder `high`.
- `condition`: optional, steuert ob der Step fuer einen Fall ausgefuehrt wird.

Beispiel fuer einen bedingten Step:

```json
{
  "expert_role": "Experte fuer hausaerztliche Leistungen fuer Chroniker",
  "model_type": "gpt-5-mini",
  "prompt_template": "experte_chronische_hausarztliche_leistungen",
  "knowledge_paths": [
    "src/ontology/gops/hausaerztlicher_versorgungsbereich/chroniker_ziffern.json"
  ],
  "condition": {
    "source": "patient",
    "field": "chronic_condition",
    "operator": "equals",
    "value": true
  }
}
```

Bedingungen werden in `runner.py` gegen Patient oder Arzt ausgewertet:

- `source`: aktuell `patient` oder `physician`.
- `field`: Feldpfad im jeweiligen Objekt, z. B. `chronic_condition` oder
  `discipline`.
- `operator`: `equals`, `not_equals`, `exists`, `not_exists`, `contains`,
  `greater_than`, `greater_or_equal`, `less_than` oder `less_or_equal`.
- `value`: Vergleichswert. Bei `exists` und `not_exists` kann der Wert fehlen.

## Neue Abrechnungspfade anlegen

1. Fachrichtung festlegen.
   - Fuer bestehende hausärztliche Versorgung ist das `general_care`.
   - Neue Fachrichtungen muessen in `src/ontology/schemas/physician.py` als
     erlaubter `MedicalDiscipline`-Wert vorhanden sein.
2. Arztdatei in `src/ontology/physicians/` anlegen oder anpassen.
   - Die Datei braucht mindestens ein Feld `discipline`.
3. Care-Path-Datei unter `src/ontology/care_paths/<discipline>.json` anlegen.
   - Der Dateiname muss exakt zur `discipline` passen.
4. GOP-Wissensdateien unter `src/ontology/gops/...` erstellen oder bestehende
   Dateien referenzieren.
5. `steps` definieren.
   - Jeder Step sollte nur die GOP-Dateien erhalten, die fuer seinen fachlichen
     Fokus relevant sind.
6. Optional `condition` setzen.
   - So laufen Spezialschritte nur fuer passende Patienten, z. B.
     Chroniker-, Palliativ- oder Geriatrie-Schritte.
7. Optional `final_step` definieren.
   - Dieser Schritt konsolidiert erfolgreiche Expertenoutputs, dedupliziert
     Vorschlaege und erstellt die finale GOP-Liste.
8. App im Debug-Modus starten und UI pruefen.
9. Danach mit echtem LLM-Aufruf testen.

## GOP-Wissensdateien

GOP-Wissensdateien folgen dem `GopList`-Schema aus
`src/ontology/schemas/gop_list.py`. Jede Datei enthaelt eine Liste von GOPs mit:

- `code`: GOP-Ziffer.
- `title`: offizieller Titel.
- `valuation`: Bewertung als `fixed` oder `categorized`.
- optional `mandatory_services`, `facultative_services`, `billing_info`.

Die Modelle bekommen diese GOP-Dateien als erlaubte Wissensbasis. In
`model_interface.py` werden Modellantworten anschliessend auf erlaubte GOP-Codes
gefiltert.

## Model-Output und Ergebnistabellen

Die Modelle liefern `ModelResponseGopList` aus `src/model_interface.py`.
Jede empfohlene GOP enthaelt:

- `code`
- `title`
- `valuation` mit patientenspezifischem `valuation_in_euro` und
  `valuation_in_points`, falls verfuegbar
- `propability`
- `rationale`

Die finale Tabelle in der App zeigt:

- `Auswahl`: Checkbox fuer die Summenberechnung.
- `GOP`
- `Titel`
- `Betrag`
- `Punkte`
- `Wahrscheinlichkeit`
- `Begruendung`

Unter der finalen Tabelle berechnet die App automatisch die Summe der Betraege
und Punkte aller ausgewaehlten GOPs. Wird eine Checkbox geaendert, rerunt
Streamlit die App und aktualisiert die Summen.

## Typischer Entwicklungsablauf

1. JSON-Daten oder Care-Path anpassen.
2. App im Debug-Modus starten:

   ```bash
   poetry run streamlit run src/app.py debug
   ```

3. Mit `Debugging Analyze` pruefen, ob Tabellen und UI weiterhin funktionieren.
4. Fuer echte Analyse `OPENAI_API_KEY` setzen.
5. App normal starten:

   ```bash
   poetry run streamlit run src/app.py
   ```

6. Einen vorhandenen oder eigenen Patienten auswaehlen und `Analyze` klicken.

## Hinweise und Stolperstellen

- `knowledge_paths` sind aktuell repo-relative Pfade wie
  `src/ontology/gops/...json`.
- Wenn eine neue Fachrichtung angelegt wird, muss sowohl die Arzt-`discipline`
  als auch die Care-Path-Datei denselben technischen Namen verwenden.
- Die UI zeigt Fachrichtungen ueber Labels aus `src/app.py` an. Neue
  Fachrichtungen koennen dort ein deutsches Label bekommen.
- Der Debug-Modus simuliert nur die Ergebnistabellen. Er prueft nicht, ob ein
  neuer Care-Path fachlich korrekt oder vollstaendig ist.
- In `model_interface.py` heisst das Wahrscheinlichkeitsfeld aktuell
  `propability`. Dieser Name muss in Dummy-Daten und Modellantworten konsistent
  bleiben.
