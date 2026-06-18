from .gop_list import StrictModel
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

MedicalDiscipline = Literal[
    'general_care',
    'chirurgie',
    'dermatologie',
    'gynaekologie',
    'radiologie',
]

class Physician(StrictModel):
    discipline: MedicalDiscipline = Field(
        description = "Medical discipline of the physician. Allowed values: general_care, chirurgie, dermatologie, gynaekologie, radiologie."
    )
