from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

OutputSchema = Literal[
    "ModelResponseGopList",
]

ReasoningEffort = Literal[
    "low",
    "medium",
    "high",
]

class Model(StrictModel):
    # Mandatory fields for all models
    expert_role: str = Field(
        description = "Description of the role of the expert, used in creating the system prompt for the model."
    )
    model_type: str = Field(
        description="Type of the model to use from openai, e.g. gpt-5.5")
    prompt_template: str = Field(
        description = "Name of the prompt template used to create the system prompt."
    )
    # Optional fields for more complex interactions
    output_schema: OutputSchema = Field(
        default = "ModelResponseGopList",
        description = "Name of the Pydantic schema used for structured model output."
    )
    task_focus: str | None = Field(
        default = None,
        description = "Description of the specific focus of the model's task, used in the system prompt."
    )
    knowledge_paths: list[str] = Field(
        default_factory = list,
        description = "List of paths to knowledge files the model can use to retrieve information. E.g. onthology/hausaerztliche_versorgung/chroniker_ziffern.json",)
    reasoning_effort: ReasoningEffort = Field(
        description = "How much reasoning effort the model should put into the answer. E.g. 'low', 'medium', 'high'.",
        default = "medium"
        )
    tools: list[str] = Field(
        description = "List of tools the model can use to retrieve information.",
        default_factory = list)
    max_output_tokens: int = Field(
        description = "Maximum number of tokens the model should output.",
        default = 1000,
        gt = 0)
    temperature: float = Field(default=0, ge=0, le=2)

ConditionSource = Literal[
    "patient",
    "physician",
    ]


Operator = Literal[
    "equals",
    "not_equals",
    "exists",
    "not_exists",
    "contains",
    "greater_than",
    "greater_or_equal",
    "less_than",
    "less_or_equal",
]

class ConditionalField(StrictModel):
    source: ConditionSource = Field(
        description="Object where the condition is evaluated, e.g. patient, physician, encounter, diagnosis."
    )

    field: str = Field(
        description="Field path inside the source object, e.g. age, chronic, contact_type, setting."
    )

    operator: Operator = Field(
        description="Comparison operator used to evaluate the condition."
    )

    value: Any | None = Field(
        default=None,
        description="Expected value. Can be omitted for exists and not_exists."
    )

class Step(Model):
    condition: None | ConditionalField = Field(
        description = "Condition for the step to be exectutet, e.g. if patient marked as 'chronic'",
        default = None)

class ProcessingPath(StrictModel):
    name: str = Field(
        description = "Name of the processing path, e.g. 'Hausärztliche Versorgung'"
    )
    steps: list[Step] = Field(
        description = "List of steps to call in sequence for this processing path."
    )
    final_step: Model | None = Field(
        default = None,
        description = "Optional final model call that consolidates all successful step outputs."
    )
