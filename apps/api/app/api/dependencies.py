from __future__ import annotations

import secrets

from fastapi import Header
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError


def require_entity(session: Session, model: type, entity_id: str, label: str):
    entity = session.get(model, entity_id)
    if entity is None:
        raise ApiError(404, "NOT_FOUND", f"{label} was not found", {"id": entity_id})
    return entity


def require_internal_write(
    x_codereason_internal: str | None = Header(default=None),
) -> None:
    """Require the shared worker token when one is configured."""

    expected = get_settings().internal_worker_token
    if expected and (
        x_codereason_internal is None
        or not secrets.compare_digest(x_codereason_internal, expected)
    ):
        raise ApiError(404, "NOT_FOUND", "Route was not found")
