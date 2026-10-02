"""Pure workflow guards shared by the GUI and tests."""

STATUSES = ["NEW", "HAS_MASTER", "APPROVED", "REJECTED", "BUILT", "READY", "PUBLISHED"]


def approve_qa2(status: str) -> str:
    """Return READY only when final outputs are awaiting the second QA gate."""
    if status != "BUILT":
        raise ValueError("QA #2 approval requires status BUILT.")
    return "READY"


def require_ready_for_publish(status: str) -> None:
    """Reject publication until an operator has completed QA #2."""
    if status != "READY":
        raise ValueError("Publish Dropbox requires status READY. Complete QA #2 first.")
