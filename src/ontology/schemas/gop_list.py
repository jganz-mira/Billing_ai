from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FixedValuation(StrictModel):
    type: Literal["fixed"] = Field(
        description="Fixed valuation for the GOP"
    )
    valuation_in_euro: float = Field(
        description="Valuation in euros"
    )
    valuation_in_points: int = Field(
        description="Valuation in points"
    )


class ValuationCategory(StrictModel):
    label: str = Field(
        description="Human-readable valuation category, e.g. age band"
    )
    valuation_in_euro: float = Field(
        description="Valuation in euros for this category"
    )
    valuation_in_points: int = Field(
        description="Valuation in points for this category"
    )


class CategorizedValuation(StrictModel):
    type: Literal["categorized"] = Field(
        description="Valuation differs by category, e.g. age band"
    )
    category_type: str = Field(
        description="Type of category, e.g. age, setting, duration"
    )
    categories: list[ValuationCategory] = Field(
        min_length=1,
        description="Valuation categories. Each category must contain euros and points."
    )


Valuation = FixedValuation | CategorizedValuation


class Gop(StrictModel):
    # The following fields are mandatory and should always be provided for each GOP code.
    code: str = Field(
        description="EBM GOP code, e.g. 03000"
    )
    title: str = Field(
        description="Official GOP title"
    )
    valuation: Valuation = Field(
        description="GOP valuation. Either fixed or categorized."
    )

    # The following fields are optional and may contain unstructured text extracted from the EBM repository.
    mandatory_services: str | None = Field(
        default=None,
        description="Obligatory service content, if available"
    )
    facultative_services: str | None = Field(
        default=None,
        description="Facultative service content, if available"
    )
    billing_info: str | None = Field(
        default=None,
        description="Raw billing rules, exclusions, frequency limits, valuation, notes"
    )


class GopList(StrictModel):
    gops: list[Gop]

# schemas for model output
class ModelResponseGop(Gop):
    rationale: str = Field(
        description="Rationale for why the GOP was recommended, including which billing-relevant facts and code features were most influential. Keep short."
    )
    propability: float = Field(
        ge=0, le=1,
        description="Model's confidence in the recommendation, between 0 and 1."
    )

class ModelResponseGopList(StrictModel):
    gops: list[ModelResponseGop]