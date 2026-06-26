from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.services.access_control import role_has_access

templates = Jinja2Templates(directory="app/templates")


def role_can(role: str, access_key: str) -> bool:
    if not role:
        return False
    with SessionLocal() as db:
        return role_has_access(db, role, access_key)


templates.env.globals["role_can"] = role_can
