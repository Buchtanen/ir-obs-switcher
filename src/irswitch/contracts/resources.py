"""Safe access to packaged machine-readable v2 contract artifacts."""

from __future__ import annotations

from importlib.resources import files

from .primitives import ContractViolation

_PACKAGED_SCHEMAS = frozenset(
    {
        "config-contract.json",
        "detector-catalog.json",
        "dto-contracts.schema.json",
        "freeze-registry.json",
    }
)


def packaged_schema_bytes(name: str) -> bytes:
    """Read one explicitly registered packaged schema without path traversal."""

    if name not in _PACKAGED_SCHEMAS:
        raise ContractViolation(f"unknown packaged v2 schema: {name!r}")
    return files("irswitch.contracts.schemas.v2").joinpath(name).read_bytes()
