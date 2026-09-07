"""SMTP/SendGrid email wrapper. Prints instead of sending in test mode."""

import os


def send_email(to: str, subject: str, body: str) -> bool:
    if os.getenv("APP_ENV") == "production":
        # TODO: implement via SMTP or SendGrid API using SENDGRID_API_KEY
        raise NotImplementedError
    print(f"[TEST MODE] EMAIL to={to} subject={subject!r}\n  body: {body}")
    return True
