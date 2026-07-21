from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, Integer, JSON, LargeBinary
from sqlalchemy import Numeric, String, Time, Uuid, inspect
from sqlalchemy.orm import Session


ModelT = TypeVar("ModelT")


def persist(session: Session, model: type[ModelT], **values: Any) -> ModelT:
    """Persist a model, filling unspecified required columns with test values."""

    mapper = inspect(model)
    for column in mapper.columns:
        key = column.key
        if key in values:
            continue
        if (
            column.primary_key
            or column.nullable
            or column.default is not None
            or column.server_default is not None
        ):
            continue
        if column.foreign_keys:
            raise AssertionError(f"required foreign key {model.__name__}.{key} was not supplied")

        column_type = column.type
        if isinstance(column_type, Enum):
            values[key] = (
                next(iter(column_type.enum_class))
                if column_type.enum_class is not None
                else column_type.enums[0]
            )
        elif isinstance(column_type, Uuid):
            values[key] = uuid4()
        elif isinstance(column_type, Boolean):
            values[key] = False
        elif isinstance(column_type, Integer):
            values[key] = 1
        elif isinstance(column_type, (Float, Numeric)):
            values[key] = Decimal("1")
        elif isinstance(column_type, JSON):
            values[key] = {}
        elif isinstance(column_type, LargeBinary):
            values[key] = b"test"
        elif isinstance(column_type, DateTime):
            values[key] = datetime.now(timezone.utc)
        elif isinstance(column_type, Date):
            values[key] = date.today()
        elif isinstance(column_type, Time):
            values[key] = time(0, 0)
        elif isinstance(column_type, String):
            values[key] = f"{model.__name__}-{key}"
        else:
            raise AssertionError(
                f"test factory needs a value for {model.__name__}.{key} ({column_type!r})"
            )

    instance = model(**values)
    session.add(instance)
    session.flush()
    return instance
