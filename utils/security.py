"""Password hashing and verification utilities.

Passwords are never stored in plain text. We use bcrypt (adaptive hash based on
Blowfish) with an auto-generated salt. The hash includes the algorithm, cost
factor and salt, so it is fully self-describing and forwards-compatible.

A stored password hash produced by ``hash_password`` always starts with ``$2``
(e.g. ``$2b$12$...``). ``verify_password`` is constant-time and safe to use
even when the stored value is not a valid bcrypt hash (it returns ``False``).
"""
from __future__ import annotations

import bcrypt

# Bcrypt cost factor. 12 is a reasonable default as of 2024 (~250ms per hash
# on commodity hardware). Increase over time as hardware gets faster.
_BCRYPT_ROUNDS = 12


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        plain_password: The plain-text password to hash.

    Returns:
        A bcrypt hash string (e.g. ``$2b$12$....``).

    Raises:
        ValueError: If the password is empty.
    """
    if not plain_password:
        raise ValueError("Password must not be empty.")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash.

    This function never raises: if ``password_hash`` is not a valid bcrypt
    hash (e.g. a legacy plain-text password), it returns ``False``. This makes
    it safe during a migration period where some rows may still contain
    non-hashed values.

    Args:
        plain_password: The plain-text password to check.
        password_hash: The stored bcrypt hash.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Not a valid bcrypt hash (e.g. legacy plaintext) -> reject.
        return False


def is_hashed(password: str | None) -> bool:
    """Check whether a stored value looks like a bcrypt hash.

    Useful for migrations and diagnostics to detect rows that still contain
    plain-text passwords.

    Args:
        password: The stored value to inspect.

    Returns:
        True if the value starts with a bcrypt prefix (``$2a$``, ``$2b$``,
        ``$2y$``), False otherwise.
    """
    if not password:
        return False
    return password.startswith(("$2a$", "$2b$", "$2y$"))