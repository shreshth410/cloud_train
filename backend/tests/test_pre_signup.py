"""Unit tests for Cognito PreSignUp Lambda trigger."""

import os
from typing import Any

import pytest

from pre_signup.main import lambda_handler


def make_cognito_event(email: str) -> dict[str, Any]:
    """Craft Cognito PreSignUp event."""
    return {
        "version": "1",
        "triggerSource": "PreSignUp_SignUp",
        "region": "ap-south-1",
        "userPoolId": "ap-south-1_mockPool",
        "userName": email,
        "callerContext": {},
        "request": {
            "userAttributes": {
                "email": email,
            }
        },
        "response": {
            "autoConfirmUser": False,
            "autoVerifyEmail": False,
        },
    }


def test_pre_signup_no_restrictions() -> None:
    """When no allowlists are set, all emails are allowed."""
    os.environ["ALLOWED_EMAIL_DOMAINS"] = ""
    os.environ["ALLOWED_EMAILS"] = ""
    ev = make_cognito_event("anyone@anywhere.com")
    res = lambda_handler(ev)
    assert res["response"]["autoConfirmUser"] is False


def test_pre_signup_domain_and_email_allowlists() -> None:
    """Domain and explicit email allowlists are strictly enforced."""
    os.environ["ALLOWED_EMAIL_DOMAINS"] = "university.edu,company.org"
    os.environ["ALLOWED_EMAILS"] = "contractor@external.com"

    # Allowed domain
    ev_domain = make_cognito_event("student@university.edu")
    assert lambda_handler(ev_domain) is not None

    # Allowed explicit email
    ev_explicit = make_cognito_event("contractor@external.com")
    assert lambda_handler(ev_explicit) is not None

    # Disallowed email
    ev_bad = make_cognito_event("intruder@random.com")
    with pytest.raises(Exception, match="Registration is restricted"):
        lambda_handler(ev_bad)


def test_pre_signup_auto_confirm() -> None:
    """AUTO_CONFIRM_USERS=true sets autoConfirmUser and autoVerifyEmail."""
    os.environ["ALLOWED_EMAIL_DOMAINS"] = ""
    os.environ["ALLOWED_EMAILS"] = ""
    os.environ["AUTO_CONFIRM_USERS"] = "true"
    try:
        ev = make_cognito_event("dev@test.com")
        res = lambda_handler(ev)
        assert res["response"]["autoConfirmUser"] is True
        assert res["response"]["autoVerifyEmail"] is True
    finally:
        os.environ["AUTO_CONFIRM_USERS"] = "false"
