"""Cognito PreSignUp Lambda trigger handler.

Enforces allowed email addresses or domains during user registration.
"""

import os
from typing import Any

from common.logging import get_logger

logger = get_logger("pre_signup")


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Verify user email against allowlists before allowing Cognito sign-up."""
    request = event.get("request", {})
    user_attrs = request.get("userAttributes", {})
    email = user_attrs.get("email", "").strip().lower()

    allowed_domains_env = os.getenv("ALLOWED_EMAIL_DOMAINS", "")
    allowed_emails_env = os.getenv("ALLOWED_EMAILS", "")
    auto_confirm = os.getenv("AUTO_CONFIRM_USERS", "false").lower() == "true"

    allowed_domains = [d.strip().lower() for d in allowed_domains_env.split(",") if d.strip()]
    allowed_emails = [e.strip().lower() for e in allowed_emails_env.split(",") if e.strip()]

    # If any restriction is configured, validate
    if allowed_domains or allowed_emails:
        if not email:
            logger.warning("Sign-up attempted with missing email attribute.")
            raise Exception("Email address is required for registration.")

        email_domain = email.split("@")[-1] if "@" in email else ""

        is_allowed = False
        if email in allowed_emails or email_domain in allowed_domains:
            is_allowed = True

        if not is_allowed:
            logger.warning(f"Registration rejected for email {email} (not in allowlist).")
            raise Exception("Registration is restricted. Your email domain or address is not permitted.")

    if auto_confirm:
        event.setdefault("response", {})
        event["response"]["autoConfirmUser"] = True
        event["response"]["autoVerifyEmail"] = True

    logger.info(f"User signup permitted for: {email}")
    return event
