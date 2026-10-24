"""Print the resolved subject and identifiers for each public sample case."""

from __future__ import annotations

import json

try:
    from . import loaders
    from .identity import resolve_identity
except ImportError:  # Allow the documented direct script invocation.
    import loaders
    from identity import resolve_identity


def main() -> None:
    identities = loaders.read_identities()
    audit = loaders.read_identity_audit()
    for case in loaders.read_requests(samples=True):
        user_id, identifiers = resolve_identity(
            case["email"], case["audit_at"], identities=identities, audit=audit
        )
        print(json.dumps({
            "case_id": case["case_id"],
            "user_id": user_id,
            "identifiers": sorted(identifiers, key=str.casefold),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
