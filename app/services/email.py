"""Email and signed-token helpers."""

import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(payload, salt: str) -> str:
    return _serializer().dumps(payload, salt=salt)


def verify_token(token: str, salt: str, max_age: int):
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email through SMTP or save it locally in development mode."""

    if current_app.config.get("MAIL_SUPPRESS_SEND", True):
        _write_to_outbox(to, subject, body)
        return False

    smtp_host = current_app.config.get("SMTP_HOST")
    smtp_port = current_app.config.get("SMTP_PORT", 587)
    smtp_user = current_app.config.get("SMTP_USER")
    smtp_password = current_app.config.get("SMTP_PASSWORD")
    mail_from = current_app.config.get("MAIL_FROM") or smtp_user

    if not all([smtp_host, smtp_user, smtp_password, mail_from]):
        raise RuntimeError(
            "SMTP configuration is incomplete. Check the .env file."
        )

    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30, context=context) as server:
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.send_message(message)

        current_app.logger.info("Invitation email successfully delivered.")
        return True

    except smtplib.SMTPAuthenticationError as error:
        current_app.logger.exception("SMTP authentication failed.")
        raise RuntimeError(
            "Gmail login failed. Use a Google App Password, "
            "not the normal Gmail password."
        ) from error

    except (smtplib.SMTPException, OSError) as error:
        current_app.logger.exception("Email delivery failed.")
        raise RuntimeError(
            f"Email could not be delivered: {error}"
        ) from error


def _write_to_outbox(to: str, subject: str, body: str) -> None:
    outbox = Path(current_app.instance_path) / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    safe_recipient = to.replace("@", "_at_").replace("/", "_")
    path = outbox / f"{timestamp}_{safe_recipient}.txt"

    path.write_text(
        f"To: {to}\nSubject: {subject}\n\n{body}\n",
        encoding="utf-8",
    )

    current_app.logger.info(
        "Development mode: invitation saved in local outbox."
    )