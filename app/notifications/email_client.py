"""SMTP/SendGrid email wrapper.

TEST MODE (default): prints instead of sending — no API key needed.
PRODUCTION MODE (APP_ENV=production): sends a real email via
SendGrid.

Callers throughout the codebase pass `to` as either a real email
address OR a customer/officer *name* (e.g. send_email(to=customer_name,
...) in app/hitl/interrupts.py) — this resolves a name to a real
address via the customers table before sending for real, so call
sites don't all need rewriting.
"""

import os


def _resolve_email_address(to: str) -> str | None:
    """If `to` already looks like an email, use it as-is. Otherwise
    look it up by name in the customers table. Returns None if it
    can't be resolved — caller should skip sending rather than error
    out an entire pipeline run over one bad recipient."""
    if "@" in to:
        return to

    try:
        from app.tools.bank_db_tools import get_customer_by_name
        customer = get_customer_by_name(to)
        return customer["email"] if customer else None
    except Exception:
        return None


def send_email(to: str, subject: str, body: str) -> bool:
    if os.getenv("APP_ENV") != "production":
        print(f"[TEST MODE] EMAIL to={to} subject={subject!r}\n  body: {body}")
        return True

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    recipient = _resolve_email_address(to)
    if recipient is None:
        print(f"[EMAIL SKIPPED] Could not resolve a real email address for '{to}'")
        return False

    message = Mail(
        from_email=os.getenv("EMAIL_FROM_ADDRESS", "noreply@disputedesk.com"),
        to_emails=recipient,
        subject=subject,
        plain_text_content=body,
    )

    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        return 200 <= response.status_code < 300
    except Exception as exc:
        print(f"[EMAIL FAILED] to={recipient}: {exc}")
        return False