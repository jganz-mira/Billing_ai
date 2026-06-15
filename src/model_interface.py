from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from ontology.schemas.gop_list import StrictModel, Valuation


class ModelResponseGop(StrictModel):
    code: str = Field(description="EBM GOP code, e.g. 03000")
    title: str = Field(description="Official GOP title")
    valuation: Valuation = Field(description="GOP valuation. Either fixed or categorized.")
    mandatory_services: str | None = None
    facultative_services: str | None = None
    billing_info: str | None = None
    rationale: str = Field(
        description=(
            "Short rationale for why the GOP was recommended, including the "
            "billing-relevant case facts."
        )
    )
    propability: float = Field(
        ge=0,
        le=1,
        description="Model confidence in the recommendation, between 0 and 1.",
    )


class ModelResponseGopList(StrictModel):
    gops: list[ModelResponseGop]


class ModelInterface:
    """Minimal OpenAI-backed interface for GOP proposal calls."""

    def __init__(self, client: Any | None = None):
        self.client = client or self._default_client()

    def propose_gops(
        self,
        *,
        model: str,
        system_prompt: str,
        case_text: str,
        patient: Any,
        physician: Any,
        gops: Any,
        reasoning_effort: str | None = None,
    ) -> ModelResponseGopList:
        allowed_codes = self._gop_codes(gops)
        prompt = self._build_prompt(
            case_text=case_text,
            patient=patient,
            physician=physician,
            gops=gops,
            allowed_codes=allowed_codes,
        )

        response_data = self._call_model(
            model=model,
            system_prompt=system_prompt,
            prompt=prompt,
            reasoning_effort=reasoning_effort,
        )
        parsed = ModelResponseGopList.model_validate(response_data)
        return ModelResponseGopList(
            gops=[gop for gop in parsed.gops if gop.code in allowed_codes]
        )

    def consolidate_gops(
        self,
        *,
        model: str,
        system_prompt: str,
        case_text: str,
        patient: Any,
        physician: Any,
        expert_outputs: list[Any],
        reasoning_effort: str | None = None,
    ) -> ModelResponseGopList:
        allowed_codes = self._expert_output_codes(expert_outputs)
        prompt = self._build_consolidation_prompt(
            case_text=case_text,
            patient=patient,
            physician=physician,
            expert_outputs=expert_outputs,
            allowed_codes=allowed_codes,
        )

        response_data = self._call_model(
            model=model,
            system_prompt=system_prompt,
            prompt=prompt,
            reasoning_effort=reasoning_effort,
        )
        parsed = ModelResponseGopList.model_validate(response_data)
        return ModelResponseGopList(
            gops=[gop for gop in parsed.gops if gop.code in allowed_codes]
        )

    def _call_model(
        self,
        *,
        model: str,
        system_prompt: str,
        prompt: str,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        responses = getattr(self.client, "responses", None)
        if responses is None:
            raise RuntimeError("The configured client does not expose responses API.")

        request: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": reasoning_effort}

        parse = getattr(responses, "parse", None)
        if parse is not None:
            response = parse(**request, text_format=ModelResponseGopList)
            parsed = getattr(response, "output_parsed", None)
            if parsed is not None:
                return parsed.model_dump()

        response = responses.create(
            **request,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "gop_proposals",
                    "schema": ModelResponseGopList.model_json_schema(),
                    "strict": True,
                }
            },
        )
        return self._extract_json(response)

    @staticmethod
    def _default_client() -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required to use ModelInterface. "
                "Install it and set OPENAI_API_KEY."
            ) from exc

        return OpenAI()

    @staticmethod
    def _build_prompt(
        *,
        case_text: str,
        patient: Any,
        physician: Any,
        gops: Any,
        allowed_codes: set[str],
    ) -> str:
        return "\n\n".join(
            [
                "Pruefe den folgenden Arztfall auf abrechenbare GOP-Ziffern.",
                "Schlage ausschliesslich GOP-Codes aus der erlaubten GOP-Liste vor.",
                f"Erlaubte GOP-Codes: {', '.join(sorted(allowed_codes))}",
                "Falltext:",
                case_text,
                "Patient:",
                json.dumps(ModelInterface._dump(patient), ensure_ascii=False, indent=2),
                "Arzt:",
                json.dumps(ModelInterface._dump(physician), ensure_ascii=False, indent=2),
                "GOP-Liste:",
                json.dumps(ModelInterface._dump(gops), ensure_ascii=False, indent=2),
            ]
        )

    @staticmethod
    def _build_consolidation_prompt(
        *,
        case_text: str,
        patient: Any,
        physician: Any,
        expert_outputs: list[Any],
        allowed_codes: set[str],
    ) -> str:
        return "\n\n".join(
            [
                "Konsolidiere die GOP-Vorschlaege der Expertenmodelle.",
                "Schlage ausschliesslich GOP-Codes vor, die in den Expertenoutputs vorkommen.",
                f"Erlaubte GOP-Codes: {', '.join(sorted(allowed_codes))}",
                "Falltext:",
                case_text,
                "Patient:",
                json.dumps(ModelInterface._dump(patient), ensure_ascii=False, indent=2),
                "Arzt:",
                json.dumps(ModelInterface._dump(physician), ensure_ascii=False, indent=2),
                "Expertenoutputs:",
                json.dumps(
                    [ModelInterface._dump(output) for output in expert_outputs],
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )

    @staticmethod
    def _gop_codes(gops: Any) -> set[str]:
        data = ModelInterface._dump(gops)
        return {str(gop["code"]) for gop in data.get("gops", []) if "code" in gop}

    @staticmethod
    def _expert_output_codes(expert_outputs: list[Any]) -> set[str]:
        codes: set[str] = set()
        for output in expert_outputs:
            data = ModelInterface._dump(output)
            for gop in data.get("gops", []):
                if "code" in gop:
                    codes.add(str(gop["code"]))
        return codes

    @staticmethod
    def _dump(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value

    @staticmethod
    def _extract_json(response: Any) -> dict[str, Any]:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return json.loads(output_text)

        if isinstance(response, dict):
            return response

        raise RuntimeError("Could not extract JSON output from model response.")
