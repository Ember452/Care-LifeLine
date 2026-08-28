from __future__ import annotations

from care_lifeline.db import session_store
from care_lifeline.db.engine import init_db


def seed() -> None:
    init_db()
    session_store.seed_demo_user()
    print("demo user seeded (demo / demo123)")


if __name__ == "__main__":
    seed()
