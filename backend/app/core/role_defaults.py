"""
Default permissions per farm membership role.
Permissions are derived from role at runtime — no SQL permission catalog.
"""

ROLE_DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    "owner": [
        "view_animals",
        "edit_animals",
        "give_feedback",
        "invite_members",
        "manage_devices",
        "manage_farm",
    ],
    "farmer": [
        "view_animals",
        "give_feedback",
    ],
    "vet": [
        "view_animals",
        "give_feedback",
    ],
}

FARM_MEMBERSHIP_ROLES = frozenset(ROLE_DEFAULT_PERMISSIONS)
MEMBERSHIP_STATUSES = frozenset({"pending", "active", "revoked"})


def permissions_for_role(role: str) -> list[str]:
    return list(ROLE_DEFAULT_PERMISSIONS.get(role, []))


def role_has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_DEFAULT_PERMISSIONS.get(role, [])
