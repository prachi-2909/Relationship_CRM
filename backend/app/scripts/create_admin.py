"""Create the first admin, or reset an existing user to admin.

    python -m app.scripts.create_admin --email you@eko.co.in --name "You" --password secret
"""

import argparse

from ..db import SessionLocal
from ..models.user import Role, User, UserStatus
from ..security.passwords import hash_password
from ..services import audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is not None:
            user.name = args.name
            user.role = Role.ADMIN
            user.status = UserStatus.ACTIVE
            user.password_hash = hash_password(args.password)
            action = "user.update"
        else:
            user = User(
                name=args.name,
                email=email,
                password_hash=hash_password(args.password),
                role=Role.ADMIN,
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.flush()
            action = "user.create"

        audit.record(
            db,
            action=action,
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            after={"email": email, "role": "admin", "via": "create_admin script"},
        )
        db.commit()
        print(f"OK - {email} is now an admin (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
