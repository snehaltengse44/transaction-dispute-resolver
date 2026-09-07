"""SMS/WhatsApp API wrapper. Prints instead of sending in test mode."""

import os


def send_sms(to: str, body: str) -> bool:
    if os.getenv("APP_ENV") == "production":
        # TODO: implement via Twilio using TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN
        raise NotImplementedError
    print(f"[TEST MODE] SMS to={to}\n  body: {body}")
    return True
