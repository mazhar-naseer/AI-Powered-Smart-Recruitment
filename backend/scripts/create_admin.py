import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Role, User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="System Admin")
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email.lower())):
            raise SystemExit("User already exists")
        db.add(User(email=args.email.lower(), full_name=args.name, password_hash=hash_password(args.password), role=Role.ADMIN, email_verified=True))
        db.commit()
        print(f"Admin created: {args.email.lower()}")


if __name__ == "__main__": main()
