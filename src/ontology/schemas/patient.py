from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .gop_list import StrictModel

ContactType = Literal[
    "personal_contact",
    "telephone_contact",
    "home_visit",
    "non_physician_assistant_contact",
]

class Patient(StrictModel):
    age: int = Field(
        description="Age of the patient in years"
    )
    contact_type: ContactType = Field(
        description=(
            "Type of contact. Allowed values: "
            "personal_contact, telephone_contact, home_visit, "
            "non_physician_assistant_contact."
        )
    )
    last_contact_date: str = Field(
        description="Date of the last contact with the patient in ISO format (YYYY-MM-DD)"
    )
    chronic_condition: bool = Field(
        description="Whether the patient has a chronic condition",
        default=False
    )
    palliative_care: bool = Field(
        description="Whether the patient is receiving palliative care",
        default=False
    )
    geriatric_patient: bool = Field(
        description="Whether the patient is considered geriatric",
        default=False
    )
