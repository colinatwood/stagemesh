from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class AdminMailer:
    """Provider-neutral governance email delivery.

    outbox mode writes RFC-822 .eml files for development/tests. smtp mode uses
    Python's standard library and starts the voting window only after the SMTP
    server accepts the message.
    """

    def __init__(self, data_dir: Path) -> None:
        self.mode = os.environ.get('STAGEMESH_ADMIN_EMAIL_MODE', 'outbox').strip().lower()
        self.outbox_dir = data_dir / 'admin-email-outbox'
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.from_address = os.environ.get('STAGEMESH_ADMIN_EMAIL_FROM', 'admin@stagemesh.local').strip()
        self.smtp_host = os.environ.get('STAGEMESH_SMTP_HOST', '').strip()
        try:
            self.smtp_port = int(os.environ.get('STAGEMESH_SMTP_PORT', '587'))
        except ValueError:
            self.smtp_port = 587
        self.smtp_user = os.environ.get('STAGEMESH_SMTP_USER', '')
        self.smtp_password = os.environ.get('STAGEMESH_SMTP_PASSWORD', '')
        self.smtp_tls = os.environ.get('STAGEMESH_SMTP_TLS', '1').strip().lower() in {'1', 'true', 'yes', 'on'}

    def status(self) -> dict[str, Any]:
        return {
            'mode': self.mode,
            'from': self.from_address,
            'smtpConfigured': bool(self.smtp_host),
            'outboxDirectory': str(self.outbox_dir) if self.mode == 'outbox' else None,
        }

    def send(self, *, recipient: str, subject: str, text: str, message_id: str) -> dict[str, Any]:
        message = EmailMessage()
        message['From'] = self.from_address
        message['To'] = recipient
        message['Subject'] = subject
        message['Message-ID'] = f'<{message_id}@stagemesh.local>'
        message.set_content(text)

        if self.mode == 'outbox':
            path = self.outbox_dir / f'{message_id}.eml'
            path.write_bytes(message.as_bytes())
            return {'accepted': True, 'acceptedAt': utc_now_iso(), 'messageId': message_id, 'mode': 'outbox', 'path': str(path)}

        if self.mode != 'smtp':
            raise RuntimeError(f'unsupported admin email mode: {self.mode}')
        if not self.smtp_host:
            raise RuntimeError('STAGEMESH_SMTP_HOST is required for smtp admin email mode')

        if self.smtp_tls:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            try:
                smtp.starttls(context=ssl.create_default_context())
                if self.smtp_user:
                    smtp.login(self.smtp_user, self.smtp_password)
                rejected = smtp.send_message(message)
            finally:
                try:
                    smtp.quit()
                except Exception:
                    pass
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            try:
                if self.smtp_user:
                    smtp.login(self.smtp_user, self.smtp_password)
                rejected = smtp.send_message(message)
            finally:
                try:
                    smtp.quit()
                except Exception:
                    pass
        if rejected:
            raise RuntimeError(f'SMTP rejected recipient: {recipient}')
        return {'accepted': True, 'acceptedAt': utc_now_iso(), 'messageId': message_id, 'mode': 'smtp'}
