from twilio.rest import Client
import random
from UnderdogCrew import settings
from datetime import datetime, timedelta
import pytz
from django.utils import timezone

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
        ist = pytz.timezone('Asia/Kolkata')
        otp_expiry_time = timezone.now().astimezone(ist) + timedelta(minutes=5)
        message = client.messages.create(
            body=f"{otp} is the OTP to verify your account with WapNeXus. OTP is valid till {otp_expiry_time.strftime('%H:%M:%S')} IST. do not share this OTP with anyone.",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return message.sid

def verify_otp(input_otp, actual_otp):
    """Verify if the input OTP matches the actual OTP."""
    return input_otp == actual_otp