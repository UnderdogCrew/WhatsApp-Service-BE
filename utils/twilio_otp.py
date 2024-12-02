from twilio.rest import Client
import random
from UnderdogCrew import settings


client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

def generate_otp():
    """Generate a 4-digit OTP."""
    if settings.SEND_LIVE_OTP:
        return random.randint(1000, 9999)
    else:
        return 1111

def send_otp(phone_number, otp):
    """Send OTP to the specified phone number using Twilio or a dummy value."""
    if settings.SEND_LIVE_OTP:
        message = client.messages.create(
            body=f"Your OTP is {otp}",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return message.sid

def verify_otp(input_otp, actual_otp):
    """Verify if the input OTP matches the actual OTP."""
    return input_otp == actual_otp