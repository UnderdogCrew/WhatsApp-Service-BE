import os
import sys
import django
from datetime import datetime, timedelta
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

def send_invoice_reminders():
    try:
        db = MongoDB()
        # Use UTC for consistency with MongoDB's ISODate
        utc_now = datetime.now(pytz.UTC)
        
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
                "name": user.get('name', ''),
                "amount": str(invoice['billing_details']['total_price']),
                "due_date": due_date.strftime("%Y-%m-%d"),
            }

            # Select appropriate message template based on days until due
      

            print(f"Sending to {user.get('name')} for invoice {invoice['invoice_number']}")

            # Send WhatsApp message
            user["phone_number"] = "7567828780"
            send_message_data(
                number=user.get('phone_number'),
                template_name="invoice_template",
                text="",
                image_url="",
                user_id=str(user['_id']),
                metadata=metadata
            )

        print("Invoice reminders sent successfully!")
        return True

    except Exception as e:
        print(f"Error sending invoice reminders: {str(e)}")
        return False

if __name__ == "__main__":
    send_invoice_reminders()