"""
Default permissions per farm membership role.
Permissions are derived from role at runtime — no SQL permission catalog.
"""

ROLE_DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    # All farm rights, including user management.
    "owner": [
        "view_animals",
        "edit_animals",
        "give_feedback",
        "invite_members",
        "manage_devices",
        "manage_geofences",
        "manage_alerts",
        "manage_farm",
        "view_farm_reports",
        "view_veterinary",
        "add_vet_observation",
    ],
    # All operational rights; no user management. Farmers apply treatments day to
    # day, so they read the vet's cases and add observation notes.
    "farmer": [
        "view_animals",
        "edit_animals",
        "give_feedback",
        "manage_devices",
        "manage_geofences",
        "manage_alerts",
        "view_veterinary",
        "add_vet_observation",
    ],
    # Veterinary write only. The vet's conclusion is the case status, so no alert
    # handling and no feedback confirmation.
    "vet": [
        "view_animals",
        "manage_veterinary",
        "view_veterinary",
    ],
}

FARM_MEMBERSHIP_ROLES = frozenset(ROLE_DEFAULT_PERMISSIONS)
MEMBERSHIP_STATUSES = frozenset({"pending", "active", "revoked"})


def permissions_for_role(role: str) -> list[str]:
    return list(ROLE_DEFAULT_PERMISSIONS.get(role, []))


def role_has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_DEFAULT_PERMISSIONS.get(role, [])
