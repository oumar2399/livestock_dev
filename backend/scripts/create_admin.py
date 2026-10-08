"""Create the first platform admin, or promote an existing account to admin.

Public registration is closed (accounts come from invitations), so the first admin
is created here, never from the app. The password is asked twice without echo and
never accepted as a command-line argument (it would stay in the shell history).

    python scripts/create_admin.py --database-url URL --email admin@example.com --name "Admin"
    python scripts/create_admin.py --database-url URL --email someone@example.com --promote
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402

MIN_PASSWORD_LENGTH = 8


def ask_password(prompt=getpass.getpass) -> str:
    password = prompt("Admin password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if prompt("Repeat password: ") != password:
        raise SystemExit("Passwords do not match.")
    return password


def main(argv=None, prompt=getpass.getpass) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database-url", required=True, help="SQLAlchemy URL of the target database")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--promote", action="store_true",
                        help="make an existing account admin instead of creating one")
    args = parser.parse_args(argv)
    email = args.email.strip().lower()

    engine = create_engine(args.database_url, hide_parameters=True)
    session = sessionmaker(bind=engine)()
    try:
        user = session.query(User).filter(User.email == email).first()
        if args.promote:
            if user is None:
                raise SystemExit(f"No account with email {email}.")
            user.role = "admin"
            session.commit()
            print(f"{email} is now a platform admin.")
            return 0
        if user is not None:
            raise SystemExit(f"An account with email {email} already exists; use --promote.")
        password = ask_password(prompt)
        session.add(User(email=email, name=args.name, role="admin", password_hash=hash_password(password)))
        session.commit()
        print(f"Admin account {email} created.")
        return 0
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
