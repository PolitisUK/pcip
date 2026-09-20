"""Central lifecycle hooks for references between analytical objects."""

from sqlalchemy.orm import Session

from .relationships import remove_object_relationships


def remove_analytical_references(db: Session, references: dict[str, set[int]]) -> None:
    """Remove canonical relationships for an explicit set of typed objects."""
    for object_type, identifiers in references.items():
        if identifiers:
            remove_object_relationships(db, object_type, identifiers)
