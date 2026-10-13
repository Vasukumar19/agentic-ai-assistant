"""Authentication, Principal Identity & Tenant Authorization Boundary."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UserPrincipal:
    """Authenticated principal representing verified identity and permissions."""
    user_id: str
    email: str
    roles: List[str] = field(default_factory=lambda: ["user"])
    is_authenticated: bool = True

    def has_role(self, role: str) -> bool:
        """Check if principal possesses a specific authorization role."""
        return role in self.roles


def get_current_principal(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_dev_user: Optional[str] = Header(None, alias="X-Dev-User"),
    x_test_user_id: Optional[str] = Header(None, alias="X-Test-User-Id"),
    x_impersonate_user: Optional[str] = Header(None, alias="X-Impersonate-User"),
) -> UserPrincipal:
    """
    Derive the verified identity principal from authentication headers.
    In production mode:
      - Strictly enforces valid API Key or verified Bearer token.
      - Test tokens (tok_test_*) and dev headers are strictly prohibited.
      - Fails closed with 401 Unauthorized if missing or invalid.
    In development & testing mode:
      - Accepts configured credentials or dev/test headers.
      - Supports query parameter 'user_id' for non-production fixture testing.
      - Defaults to local developer principal 'usr_dev' if no credentials provided.
    """
    token = bearer.credentials if bearer else None
    principal: Optional[UserPrincipal] = None

    is_non_prod = (
        settings.AUTH_MODE in ("development", "testing")
        and settings.ENVIRONMENT in ("development", "testing")
    )

    # 1. API Key validation
    if x_api_key and isinstance(x_api_key, str):
        if settings.AUTH_API_KEYS and x_api_key in settings.AUTH_API_KEYS:
            # Deterministic, collision-resistant identity from SHA-256 of API key
            key_hash = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()[:16]
            principal = UserPrincipal(
                user_id=f"usr_apikey_{key_hash}",
                email=f"apikey_{key_hash}@system",
                roles=["user", "service"],
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_CREDENTIALS", "message": "Provided API key is invalid or revoked."},
            )

    # 2. Bearer Token validation
    if not principal and token and isinstance(token, str):
        if is_non_prod:
            if token.startswith("tok_test_admin_"):
                principal = UserPrincipal(
                    user_id=token.replace("tok_test_admin_", "usr_"),
                    email=f"{token}@test",
                    roles=["admin", "user"],
                )
            elif token.startswith("tok_test_user_"):
                uid = token.replace("tok_test_user_", "usr_")
                principal = UserPrincipal(
                    user_id=uid,
                    email=f"{uid}@test",
                    roles=["user"],
                )
            elif len(token) >= 8:
                principal = UserPrincipal(
                    user_id=f"usr_{token[:8]}",
                    email=f"user_{token[:8]}@local",
                    roles=["user"],
                )
        else:
            # In production: test tokens are STRICTLY REJECTED
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_TOKEN", "message": "Bearer token is invalid or expired."},
            )

    # 3. Environment-specific development & test fallbacks
    if not principal:
        if is_non_prod:
            # Check explicit test headers first
            effective_uid = None
            if isinstance(x_test_user_id, str):
                effective_uid = x_test_user_id
            elif isinstance(x_dev_user, str):
                effective_uid = x_dev_user

            if not effective_uid:
                # Check query parameter for dev/test mode convenience
                effective_uid = request.query_params.get("user_id")
            if not effective_uid:
                effective_uid = "usr_dev"

            principal = UserPrincipal(
                user_id=effective_uid,
                email=f"{effective_uid}@test.local" if settings.AUTH_MODE == "testing" else f"{effective_uid}@local",
                roles=["user"],
            )
        else:
            # Production without valid credentials: FAIL CLOSED
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "UNAUTHENTICATED", "message": "Authentication required to access protected resource."},
            )

    # 4. Explicit Administrative Impersonation
    if x_impersonate_user and isinstance(x_impersonate_user, str):
        if not principal.has_role("admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": "IMPERSONATION_DENIED",
                    "message": "Administrative role required to impersonate user identity.",
                },
            )
        logger.warning(
            "Admin principal '%s' impersonating user '%s'", principal.user_id, x_impersonate_user
        )
        return UserPrincipal(
            user_id=x_impersonate_user,
            email=f"{x_impersonate_user}@impersonated",
            roles=["user"],
        )

    return principal


def verify_resource_ownership(
    resource_owner_id: str,
    principal: UserPrincipal,
    resource_type: str = "resource",
) -> None:
    """
    Ensure the authenticated principal owns the requested resource.
    Admins are permitted access; non-owners receive a 403 Forbidden.
    """
    if principal.user_id != resource_owner_id and not principal.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "FORBIDDEN",
                "message": f"Tenant isolation violation: Current user does not own this {resource_type}.",
            },
        )
