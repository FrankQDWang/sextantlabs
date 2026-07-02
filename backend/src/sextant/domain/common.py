from __future__ import annotations


class DomainError(Exception):
    """Base exception for domain-layer failures."""


class DomainInvariantError(DomainError):
    """Raised when a domain invariant would be violated."""


class InvalidStateTransition(DomainError):
    """Raised when an object is moved through an illegal lifecycle transition."""
