"""Authentication backend abstraction.

The rest of the app only ever calls ``AuthBackend.authenticate`` — swapping
local passwords for LDAP/AD bind auth later means writing one new class that
returns the matching :class:`~server_app.models.User` row (creating it on
first login if needed) and wiring it up in ``create_app``. Tokens, RBAC and
job isolation are unaffected by the swap.

Sketch for the future LDAP backend (not implemented in this phase)::

    class LdapAuthBackend:
        def authenticate(self, session, username, password):
            if not ldap_bind(self._url, f"uid={username},{self._base_dn}", password):
                return None
            return get_or_provision_user(session, username)
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from server_app.auth.passwords import hash_password, needs_rehash, verify_password
from server_app.models import User


class AuthBackend(Protocol):
    def authenticate(self, session: Session, username: str, password: str) -> User | None:
        """Return the active user on success, ``None`` on any failure.

        Implementations must not leak *why* authentication failed.
        """
        ...


class LocalAuthBackend:
    """Argon2id-verified credentials from the local ``users`` table."""

    def authenticate(self, session: Session, username: str, password: str) -> User | None:
        user = session.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()
        if user is None:
            # burn comparable time so absent users aren't detectable by timing
            verify_password(_DUMMY_HASH, password)
            return None
        if not verify_password(user.password_hash, password):
            return None
        if not user.is_active:
            return None
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        return user


_DUMMY_HASH = hash_password("timing-equalizer-dummy")
