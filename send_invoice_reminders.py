import os
import sys
import django
from datetime import datetime, timedelta
from twilio.rest import Client
import pytz
from bson import ObjectId
current_path = os.path.abspath(os.getcwd())
base_path = os.path.dirname(current_path)

# Set up Django environment
sys.path.append(base_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from utils.database import MongoDB
from utils.whatsapp_message_data import send_message_data
from utils.twilio_otp import send_sms_message

def send_sms_message_invoice(to_number, metadata, user_id, invoice_id):
    try:
        # Format message based on template
        message_body = (
            f"Hello {metadata['name']},\n\n"
            f"This is a friendly reminder that your bill of ₹{metadata['amount']} is due on {metadata['due_date']}. "
            "Kindly make the payment to avoid any service interruptions.\n\n"
            "You can pay using Pay Now.\n\n"
            "If you've already made the payment, please ignore this message. Let us know if you need any assistance.\n\n"
            "Thank you!\n"
            "WapNexus"
        )
        
        # Send SMS message
        message , message_sid = send_sms_message(
            to_number=to_number,
            message_body=message_body
        )
        
        # Store in database
        if message_sid:
            db = MongoDB()
            sms_record = {
                'user_id': user_id,
                'invoice_id': invoice_id,
                'phone_number': to_number,
                'message': message_body,
                'message_sid': message_sid,
                'status': 'sent',
                'type': 'invoice_reminder',
                'metadata': metadata,
                'created_at': datetime.now(pytz.UTC),
                'updated_at': datetime.now(pytz.UTC)
            }   
            db.create_document('sms_logs', sms_record)
        return True
        
    except Exception as e:
        # Log failed attempt
        error_record = {
            'user_id': user_id,
            'invoice_id': invoice_id,
            'phone_number': to_number,
            'message': message_body,
            'error': str(e),
            'status': 'failed',
            'type': 'invoice_reminder',
            'metadata': metadata,
            'created_at': datetime.now(pytz.UTC),
            'updated_at': datetime.now(pytz.UTC)
        }
        db.create_document('sms_logs', error_record)
        print(f"Error sending SMS: {str(e)}")
        return False


def send_invoice_reminders():
    try:
        db = MongoDB()
        # Use UTC for consistency with MongoDB's ISODate
        utc_now = datetime.now(pytz.UTC)
        
        # First, handle overdue invoices and deactivate accounts
        overdue_invoices = db.find_documents('invoices', {
            "payment_status": "Pending",
            "due_date": {"$lt": utc_now.replace(hour=0, minute=0, second=0, microsecond=0)}
        })

        print(f"Found {len(list(overdue_invoices))} overdue invoices")
        
        # Deactivate accounts with overdue invoices
        for invoice in overdue_invoices:
            user_id = invoice.get('user_id')
            if user_id:
                print(f"Deactivating account for user {user_id} due to overdue invoice {invoice.get('invoice_number')}")
                db.update_document('users',
                    {"_id": ObjectId(user_id)},
                    {"is_active": False, "updated_at": utc_now}
                )

        # Continue with regular reminder logic
        # Define reminder days before due date
        reminder_days = {0, 1, 2}  # Send reminders on due date, 1 day before, 2 days before
        
        # Calculate target dates for reminders
        target_dates = [utc_now + timedelta(days=day) for day in reminder_days]
        target_dates = [d.replace(hour=0, minute=0, second=0, microsecond=0) for d in target_dates]
        
        print("Checking for invoices due on:", [d.strftime("%Y-%m-%d") for d in target_dates])

        # Fetch unpaid invoices
        unpaid_invoices = db.find_documents('invoices', {
            "payment_status": "Pending",
            "due_date": {
                "$gte": utc_now.replace(hour=0, minute=0, second=0, microsecond=0),
                "$lte": utc_now + timedelta(days=max(reminder_days))
            }
        })

        print(f"Found {len(list(unpaid_invoices))} unpaid invoices")

        for invoice in unpaid_invoices:
            # Fetch user details
            user = db.find_document('users', {"_id": ObjectId(invoice['user_id'])})
            if not user:
                print(f"User not found for invoice {invoice.get('invoice_number')}")
                continue
            print(user)
            # Calculate days until due date
            due_date = invoice['due_date']
            if isinstance(due_date, str):
                due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
            days_until_due = (due_date.replace(tzinfo=pytz.UTC) - utc_now).days

            print(f"Invoice {invoice['invoice_number']} is due in {days_until_due} days")

            # Prepare message metadata
            metadata = {
                "name": user['first_name'] + " " + user['last_name'],
                "amount": str(invoice['billing_details']['total_price']),
                "due_date": due_date.strftime("%Y-%m-%d"),
            }

            # Select appropriate message template based on days until due
            print(f"Sending to {metadata.get('name')} for invoice {invoice['invoice_number']}")

            # Clean phone number by removing country code
            phone_number = user.get('business_number', '')
            if phone_number.startswith('+'):
                phone_number = phone_number[3:]  # Remove '+91' or other country codes
            elif phone_number.startswith('91'):
                phone_number = phone_number[2:]  # Remove '91'
            print("business_number", phone_number)
            
            send_sms_message_invoice(
                to_number=phone_number,
                metadata=metadata,
                user_id=str(user['_id']),
                invoice_id=invoice['invoice_number']
            )

            # send_message_data(
            #     number=phone_number,
            #     template_name="invoice",
            #     text="",
            #     image_url="",
            #     user_id=str(user['_id']),
            #     metadata=metadata
            # )

        print("Invoice reminders sent successfully!")
        return True

    except Exception as e:
        print(f"Error sending invoice reminders: {str(e)}")
        return False

if __name__ == "__main__":
    send_invoice_reminders()