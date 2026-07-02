from django.template.loader import render_to_string
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from UnderdogCrew import settings


def send_email(to_email, subject, html_content, from_email=None, from_name=None):
    """
    Send an HTML email via SendGrid.

    Returns a dict with status_code, body, and headers on success.
    Raises the underlying SendGrid exception on failure.
    """
    from_addr = from_email or settings.SENDGRID_FROM_EMAIL
    from_display = from_name if from_name is not None else settings.SENDGRID_FROM_NAME
    from_email_value = (from_addr, from_display) if from_display else from_addr

    message = Mail(
        from_email=from_email_value,
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )

    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        # sg.set_sendgrid_data_residency("eu")
        # uncomment the above line if you are sending mail using a regional EU subuser
        response = sg.send(message)
        return {
            'status_code': response.status_code,
            'body': response.body,
            'headers': response.headers,
        }
    except Exception as e:
        error_message = getattr(e, 'body', None) or getattr(e, 'message', None) or str(e)
        raise type(e)(error_message) from e


def send_password_reset_email(to_email, reset_link, user_name=None):
    display_name = user_name or to_email.split('@')[0]
    html_content = render_to_string('emails/password_reset.html', {
        'user_name': display_name,
        'reset_link': reset_link,
    })

    return send_email(
        to_email=to_email,
        subject='Reset your WapNexus password',
        html_content=html_content,
    )
