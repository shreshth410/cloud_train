#!/usr/bin/env python3
"""Create demo user in Cognito for smoke tests and live evaluation."""

import argparse
import os
import sys

import boto3
from botocore.exceptions import ClientError


def create_demo_user(
    user_pool_id: str, email: str, password: str, region: str = "ap-south-1"
) -> None:
    client = boto3.client("cognito-idp", region_name=region)
    print(f"Creating confirmed demo user {email} in User Pool {user_pool_id}...")

    try:
        # Create user (suppress welcome email for programmatic testing)
        client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
        )
        print("  ✅ User created successfully.")
    except client.exceptions.UsernameExistsException:
        print("  ℹ️ User already exists. Setting password...")
    except ClientError as e:
        print(f"  ❌ Failed to create user: {e}")
        sys.exit(1)

    try:
        # Set permanent password so force-change is not required on first sign-in
        client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
        print("  ✅ Password set permanently (confirmed).")
    except ClientError as e:
        print(f"  ❌ Failed to set user password: {e}")
        sys.exit(1)

    print(f"\n🎉 Demo user {email} is ready to authenticate!\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an admin-confirmed test user in AWS Cognito."
    )
    parser.add_argument(
        "--pool-id", default=os.getenv("USER_POOL_ID"), help="Cognito User Pool ID"
    )
    parser.add_argument(
        "--email", default=os.getenv("DEMO_USER_EMAIL"), help="Demo user email"
    )
    parser.add_argument(
        "--password", default=os.getenv("DEMO_USER_PASSWORD"), help="Demo user password"
    )
    parser.add_argument(
        "--region", default=os.getenv("AWS_REGION", "ap-south-1"), help="AWS Region"
    )
    args = parser.parse_args()

    if not args.pool_id or not args.email or not args.password:
        print(
            "Error: --pool-id, --email, and --password must be provided via arguments or environment variables."
        )
        sys.exit(1)

    create_demo_user(args.pool_id, args.email, args.password, args.region)


if __name__ == "__main__":
    main()
