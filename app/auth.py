import hmac
import os
from functools import lru_cache
from urllib.parse import quote

import jwt
import requests
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import csv_env, origins

bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def jwks_client(issuer: str):
    return jwt.PyJWKClient(issuer.rstrip("/") + "/.well-known/jwks.json", timeout=5)


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    if not credentials:
        raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    issuer = os.getenv("CLERK_ISSUER", "").rstrip("/")
    if not issuer.startswith("https://"):
        raise HTTPException(503, "Authentication is not configured")
    try:
        key = os.getenv("CLERK_JWT_KEY")
        if key:
            key = key.replace("\\n", "\n")
        else:
            key = jwks_client(issuer).get_signing_key_from_jwt(credentials.credentials).key
        claims = jwt.decode(
            credentials.credentials, key, algorithms=["RS256"], issuer=issuer,
            options={"require": ["exp", "nbf", "iat", "iss", "sub", "azp"], "verify_aud": False},
            leeway=5,
        )
        if claims["azp"] not in csv_env("CLERK_AUTHORIZED_PARTIES", ",".join(origins())):
            raise jwt.InvalidTokenError("Untrusted origin")
        if claims.get("sts") == "pending" or not claims["sub"].startswith("user_"):
            raise jwt.InvalidTokenError("Incomplete session")
        return claims["sub"]
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Authentication temporarily unavailable") from None
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        raise HTTPException(401, "Invalid or expired session") from None


def verified_email(user_id: str) -> str:
    secret = os.getenv("CLERK_SECRET_KEY")
    if not secret:
        raise HTTPException(503, "Email verification is not configured")
    try:
        response = requests.get(
            "https://api.clerk.com/v1/users/" + quote(user_id, safe=""),
            headers={"Authorization": "Bearer " + secret}, timeout=5,
        )
        response.raise_for_status()
        user = response.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(503, "Unable to verify email right now") from None
    primary = user.get("primary_email_address_id")
    for email in user.get("email_addresses", []):
        if email.get("id") == primary and email.get("verification", {}).get("status") == "verified":
            return email["email_address"]
    raise HTTPException(403, "Verify your primary email before saving alerts")


def admin_user(user_id: str = Depends(current_user)) -> str:
    if user_id not in csv_env("ADMIN_USER_IDS"):
        raise HTTPException(403, "Administrator access required")
    return user_id


def verify_api_key(x_api_key: str | None = Header(None)):
    expected = os.getenv("SCRAPE_SECRET_KEY")
    if not expected:
        raise HTTPException(503, "Scraping is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(403, "Invalid or missing API key")
