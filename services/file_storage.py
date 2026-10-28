from uuid import UUID, uuid4

from flask import session


def get_session_owner_id(*, create: bool) -> str | None:
    owner_id = session.get("file_owner_id")
    try:
        return UUID(hex=owner_id).hex
    except (TypeError, ValueError):
        if not create:
            return None

    owner_id = uuid4().hex
    session["file_owner_id"] = owner_id
    return owner_id
