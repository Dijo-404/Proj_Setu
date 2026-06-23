from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Role, User
from app.security import hash_password
from app.services.settings import ensure_company_records, ensure_default_settings


def bootstrap(db: Session) -> None:
    ensure_default_settings(db)
    ensure_company_records(db)
    if db.scalar(select(User.id).limit(1)):
        return
    settings = get_settings()
    db.add(
        User(
            username=settings.bootstrap_admin_username.strip().lower(),
            password_hash=hash_password(settings.bootstrap_admin_password),
            role=Role.SUPER_ADMIN.value,
            active=True,
        )
    )
    db.commit()
