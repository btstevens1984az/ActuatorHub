from __future__ import annotations

from fastapi import Header, HTTPException

from .models import Role, User
from .store import store

ROLE_RANK = {
    Role.viewer: 1,
    Role.operator: 2,
    Role.approver: 3,
    Role.admin: 4,
}


def get_user(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> User:
    if not x_user_id or x_user_id not in store.users:
        raise HTTPException(status_code=401, detail="Provide a valid X-User-Id header")
    return store.users[x_user_id]


def require_role(user: User, minimum: Role) -> None:
    if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{user.role.value}' cannot perform this action (needs {minimum.value}+)",
        )
