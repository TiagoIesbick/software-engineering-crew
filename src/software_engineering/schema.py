from pydantic import BaseModel, constr
from typing import Optional


class ModuleSpec(BaseModel):
    name: constr(pattern=r'.+\.py$')      # must end with .py
    class_name: constr(pattern=r'^[A-Z][A-Za-z0-9_]*$')  # valid class name


class ProjectSpec(BaseModel):
    modules: list[ModuleSpec]
    frontend: Optional[bool] = True
