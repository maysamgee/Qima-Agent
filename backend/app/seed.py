from sqlalchemy import select

from app.config import get_settings
from app.database import session_factory
from app.integrations.demo import demo_profiles
from app.models import User
from app.repositories import upsert_candidate
from app.scoring import calculate, seed_policies


def seed():
    settings = get_settings()
    with session_factory()() as db:
        seed_policies(db)
        if settings.app_env in {"local", "test"}:
            if not db.scalar(select(User).where(User.subject == "local-admin")):
                db.add(User(subject="local-admin", name="Local development user", roles=["ADMIN"]))
            for mode in ["LEAD", "SOURCING"]:
                for profile in demo_profiles(mode):
                    candidate, _ = upsert_candidate(db, profile, mode, None)
                    calculate(db, candidate)
        db.commit()


if __name__ == "__main__":
    seed()
