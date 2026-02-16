from __future__ import annotations


def is_descendant_of(child: object, ancestor: object) -> bool:
    current = child
    while current is not None:
        if current is ancestor:
            return True
        parent_getter = getattr(current, "parent", None)
        if not callable(parent_getter):
            return False
        current = parent_getter()
    return False
