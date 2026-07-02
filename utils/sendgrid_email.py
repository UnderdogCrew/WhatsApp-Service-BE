from django.template.loader import render_to_string
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from UnderdogCrew import settings


def send_password_reset_email(to_email, reset_link, user_name=None):
    display_name = user_name or to_email.split('@')[0]
    html_content = render_to_string('emails/password_reset.html', {
        'user_name': display_name,
        'reset_link': reset_link,
    })

    message = Mail(
        from_email=Email(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
        to_emails=To(to_email),
        subject='Reset your WapNexus password',
        html_content=Content('text/html', html_content),
    )

    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    response = sg.send(message)
    return response.status_code
