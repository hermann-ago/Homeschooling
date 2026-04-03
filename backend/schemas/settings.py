from pydantic import BaseModel
from datetime import date

class SchoolYearSettings(BaseModel):
    start_date: date
    end_date: date
