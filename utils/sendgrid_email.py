import base64
import json
import logging
from pathlib import Path

from django.template.loader import render_to_string
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    ContentId,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)
from UnderdogCrew import settings

logger = logging.getLogger(__name__)

WAPNEXUS_LOGO_CID = 'wapnexus_logo'
WAPNEXUS_LOGO_PATH = (
    Path(__file__).resolve().parent.parent
    / 'login_apis'
    / 'static'
    / 'emails'
    / 'wapnexus-logo.png'
)


def _parse_sendgrid_error(exc):
    error_body = getattr(exc, 'body', None)
    if isinstance(error_body, bytes):
        error_body = error_body.decode()
    if isinstance(error_body, str):
        try:
            parsed = json.loads(error_body)
            messages = [e.get('message', '') for e in parsed.get('errors', []) if e.get('message')]
            if messages:
                return '; '.join(messages)
        except json.JSONDecodeError:
            return error_body
    return getattr(exc, 'message', None) or str(exc)


def _add_inline_attachment(message, file_path, content_id):
    encoded = base64.b64encode(file_path.read_bytes()).decode()
    message.add_attachment(Attachment(
        FileContent(encoded),
        FileName(file_path.name),
        FileType('image/png'),
        Disposition('inline'),
        ContentId(content_id),
    ))


def send_email(to_email, subject, html_content, from_email=None, from_name=None, inline_attachments=None):
    """
    Send an HTML email via SendGrid.

    Returns a dict with status_code, body, and headers on success.
    Raises the underlying SendGrid exception on failure.
    """
    api_key = (settings.SENDGRID_API_KEY or '').strip()
    if not api_key:
        raise ValueError('SENDGRID_API_KEY is not configured')

    from_addr = (from_email or settings.SENDGRID_FROM_EMAIL or '').strip()
    if not from_addr:
        raise ValueError('SENDGRID_FROM_EMAIL is not configured')

    from_display = from_name if from_name is not None else settings.SENDGRID_FROM_NAME
    from_email_value = (from_addr, from_display) if from_display else from_addr

    message = Mail(
        from_email=from_email_value,
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )

    for attachment in inline_attachments or []:
        _add_inline_attachment(message, attachment['path'], attachment['content_id'])

    try:
        sg = SendGridAPIClient(api_key)
        # sg.set_sendgrid_data_residency("eu")
        # uncomment the above line if you are sending mail using a regional EU subuser
        response = sg.send(message)
        body = response.body.decode() if isinstance(response.body, bytes) else response.body
        return {
            'status_code': getattr(response, 'status_code', None) or getattr(response, 'code', None),
            'body': body,
            'headers': response.headers,
        }
    except Exception as e:
        error_message = _parse_sendgrid_error(e)
        logger.error(
            'SendGrid email failed (to=%s, from=%s): %s',
            to_email,
            from_addr,
            error_message,
        )
        raise type(e)(error_message) from e


def send_password_reset_email(to_email, reset_link, user_name=None):
    display_name = user_name or to_email.split('@')[0]
    html_content = render_to_string('emails/password_reset.html', {
        'user_name': display_name,
        'reset_link': reset_link,
    })

    inline_attachments = []
    if WAPNEXUS_LOGO_PATH.exists():
        inline_attachments.append({
            'path': WAPNEXUS_LOGO_PATH,
            'content_id': WAPNEXUS_LOGO_CID,
        })

    return send_email(
        to_email=to_email,
        subject='Reset your WapNexus password',
        html_content=html_content,
        inline_attachments=inline_attachments,
    )
