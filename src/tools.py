from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import Field

try:
    from .ontology.schemas.gop_list import Gop, GopList, StrictModel
except ImportError:
    from ontology.schemas.gop_list import Gop, GopList, StrictModel


class GopLookupInput(StrictModel):
    codes: list[str] = Field(
        min_length=1,
        description="GOP codes that should be loaded from the configured GOP files.",
    )


class GopLookupTool:
    """Load selected GOP definitions from a configurable set of GOP JSON files."""

    name = "load_gops"
    description = (
        "Loads selected GOP definitions by GOP code from configured GOP JSON files "
        "and returns them as GopList."
    )

    def __init__(self, searchable_paths: Iterable[str | Path]):
        self.searchable_paths = [Path(path) for path in searchable_paths]
        self._index: dict[str, Gop] | None = None

    def load_gops(self, codes: Iterable[str]) -> GopList:
        requested_codes = _normalize_codes(codes)
        index = self._load_index()
        return GopList(gops=[index[code] for code in requested_codes if code in index])

    def missing_codes(self, codes: Iterable[str]) -> list[str]:
        requested_codes = _normalize_codes(codes)
        index = self._load_index()
        return [code for code in requested_codes if code not in index]

    def available_codes(self) -> list[str]:
        return sorted(self._load_index())

    def __call__(self, codes: Iterable[str]) -> GopList:
        return self.load_gops(codes)

    @classmethod
    def tool_schema(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "name": cls.name,
            "description": cls.description,
            "parameters": GopLookupInput.model_json_schema(),
        }

    def _load_index(self) -> dict[str, Gop]:
        if self._index is not None:
            return self._index

        index: dict[str, Gop] = {}
        for path in self.searchable_paths:
            gop_list = GopList.model_validate(_load_json(path))
            for gop in gop_list.gops:
                index.setdefault(gop.code, gop)

        self._index = index
        return index


def load_gops_by_code(
    codes: Iterable[str],
    searchable_paths: Iterable[str | Path],
) -> GopList:
    return GopLookupTool(searchable_paths).load_gops(codes)


def _normalize_codes(codes: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for code in codes:
        normalized_code = str(code).strip()
        if not normalized_code or normalized_code in seen:
            continue
        seen.add(normalized_code)
        normalized.append(normalized_code)
    return normalized


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)
