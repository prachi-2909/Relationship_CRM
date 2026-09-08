"""User administration. Admin only."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.user import Role, User, UserStatus
from ...schemas.user import UserCreate, UserOut, UserUpdate
from ...security.deps import require_roles
from ...security.passwords import hash_password
from ...services import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor.id,
        after={"email": user.email, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    before = {
        "name": user.name,
        "role": user.role.value,
        "status": user.status.value,
    }
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        user.name = data["name"]
    if "role" in data:
        user.role = data["role"]
    if "status" in data:
        user.status = data["status"]
    after = {
        "name": user.name,
        "role": user.role.value,
        "status": user.status.value,
    }

    audit.record(
        db,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor.id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(user)
    return user
