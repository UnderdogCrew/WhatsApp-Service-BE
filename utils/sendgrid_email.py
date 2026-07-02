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
        print(response)
        # Make sure body is decoded to string if it's bytes
        body = response.body.decode() if isinstance(response.body, bytes) else response.body
        return {
            'status_code': getattr(response, 'status_code', None) or getattr(response, 'code', None),
            'body': body,
            'headers': response.headers,
        }
    except Exception as e:
        # The error "'bytes' object has no attribute 'code'" suggests we're trying to access .code on a bytes object (probably SendGrid error response)
        # Provide clearer error with decoding if needed
        error_body = getattr(e, 'body', None)
        if isinstance(error_body, bytes):
            error_message = error_body.decode()
        elif error_body is not None:
            error_message = error_body
        else:
            error_message = getattr(e, 'message', None) or str(e)
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
