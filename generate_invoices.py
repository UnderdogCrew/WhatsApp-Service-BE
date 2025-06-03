import os
import django
from datetime import datetime, timedelta
from django.utils import timezone
import pytz
import calendar
from bson.objectid import ObjectId
# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from utils.database import MongoDB
from utils.auth import current_dollar_price
from utils.twilio_otp import send_sms_message

def generate_monthly_invoices():
    """
    Generate monthly invoices for all users
    """
    try:
        ist = pytz.timezone('Asia/Kolkata')
        print(f"Starting invoice generation at {timezone.now().astimezone(ist)}")
        db = MongoDB()
        dollar_price = current_dollar_price()
        
        # Calculate date range for the previous month
        today = timezone.now().astimezone(ist)
        # Get first day of previous month
        first_day = (today.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Get last day of previous month using calendar
        _, last_day_of_month = calendar.monthrange(first_day.year, first_day.month)
        last_day = first_day.replace(day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999)
        
        print(f"Checking invoices for period: {first_day} - {last_day}")
        
        # Get all users
        users = db.find_documents('users', {})

        for user in users:
            user_id = str(user['_id'])
            
            # Check if invoice already exists for this user and period
            existing_invoice = db.find_documents('invoices', {
                "user_id": user_id,
                "billing_period": f"{first_day.strftime('%B %d')} - {last_day.strftime('%B %d, %Y')}"
            })
            
            if existing_invoice:
                print(f"Invoice already exists for user {user_id} for period {first_day.strftime('%B %d')} - {last_day.strftime('%B %d, %Y')}")
                continue
            
            print(f"Processing user {user_id}")
            # Build filter conditions
            filters = {
                "user_id": user_id,
                "created_at": {"$gte": first_day, "$lte": last_day}
            }

            # Calculate totals from different services
            whatsapp_logs = db.find_documents('whatsapp_message_logs', filters)
            whatsapp_total = sum(log.get('price', 0) for log in whatsapp_logs)
            print(f"Whatsapp total: {whatsapp_total}")
            image_logs = db.find_documents('image_generation_logs', filters)
            image_total = sum(log.get('price', 0) for log in image_logs)
            image_total = dollar_price * image_total
            print(f"Image total: {image_total}")
            text_logs = db.find_documents('text_generation_logs', filters)
            text_total = sum(log.get('price', 0) for log in text_logs)
            text_total = dollar_price * text_total

            total_price = whatsapp_total + image_total + text_total
            
            # Calculate GST
            cgst = round(total_price * 0.09, 2)  # 9% CGST
            sgst = round(total_price * 0.09, 2)  # 9% SGST
            total_price_with_tax = round(total_price + cgst + sgst, 2)
            
            billing_period = f"{first_day.strftime('%B %d')} - {last_day.strftime('%B %d, %Y')}"

            invoice_data = {
                "user_id": user_id,
                "account_id": user.get('account_id', ''),
                "billing_period": billing_period,
                "created_at": last_day.astimezone(ist),
                "billing_details": {
                    "whatsapp_total": round(whatsapp_total, 2),
                    "image_total": round(image_total, 2),
                    "text_total": round(text_total, 2),
                    "subtotal": round(total_price, 2),
                    "cgst": cgst,
                    "sgst": sgst,
                    "total_price": total_price_with_tax
                },
                "status": "Generated",
                "payment_status": "Pending",
                "due_date": last_day.astimezone(ist) + timedelta(days=7),
                "invoice_number": f"INV-{user.get('account_id', '')}-{today.strftime('%Y%m')}"
            }

            if total_price == 0:
                invoice_data["payment_status"] = "Paid"    
            
            db.create_document('invoices', invoice_data)
            print(f"Generated invoice for user {user_id} for period {billing_period}")
            print(f"Subtotal: {total_price}, CGST: {cgst}, SGST: {sgst}, Total with tax: {total_price_with_tax}")

            # After successfully generating the invoice, send SMS
            # Prepare metadata
            metadata = {
                "name": user.get('first_name', '') + " " + user.get('last_name', ''),
                "amount": str(invoice_data['billing_details']['total_price']),
                "due_date": invoice_data['due_date'].strftime("%d/%m/%Y") if hasattr(invoice_data['due_date'], 'strftime') else invoice_data['due_date'],
                "invoice_number": invoice_data['invoice_number']
            }
            
            # Clean phone number by removing country code
            phone_number = user.get('business_number', '')
            if phone_number.startswith('+'):
                phone_number = phone_number[3:]  # Remove '+91' or other country codes
            elif phone_number.startswith('91'):
                phone_number = phone_number[2:]  # Remove '91'
            
            # Send SMS notification
            send_sms_message_invoice_generated(
                to_number=phone_number,
                metadata=metadata,
                user_id=str(user['_id']),
                invoice_id=invoice_data['invoice_number']
            )

        print("Monthly invoice generation completed successfully")
        return True

    except Exception as e:
        print(f"Error generating monthly invoices: {str(e)}")
        return False

def send_sms_message_invoice_generated(to_number, metadata, user_id, invoice_id):
    try:
        # Format message for invoice generation
        message_body = (
            f"Hello {metadata['name']},\n\n"
            f"Your invoice #{metadata['invoice_number']} has been generated successfully!\n\n"
            f"Invoice Details:\n"
            f"Amount: ₹{metadata['amount']}\n"
            f"Due Date: {metadata['due_date']}\n\n"
            f"Please make the payment before the due date to avoid any service interruptions.\n\n"
            f"You can view and pay your invoice in your wapnexus dashboard.\n\n"
            f"Thank you for your business!\n"
            f"WapNexus Team"
        )
        
        # Send SMS message
        message, message_sid = send_sms_message(
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
                'type': 'invoice_generated',
                'metadata': metadata,
                'created_at': datetime.now(pytz.UTC),
                'updated_at': datetime.now(pytz.UTC)
            }   
            db.create_document('sms_logs', sms_record)
            print(f"Invoice generation SMS sent successfully! SID: {message_sid}")
        return True
        
    except Exception as e:
        # Log failed attempt
        try:
            db = MongoDB()
            error_record = {
                'user_id': user_id,
                'invoice_id': invoice_id,
                'phone_number': to_number,
                'message': message_body,
                'error': str(e),
                'status': 'failed',
                'type': 'invoice_generated',
                'metadata': metadata,
                'created_at': datetime.now(pytz.UTC),
                'updated_at': datetime.now(pytz.UTC)
            }
            db.create_document('sms_logs', error_record)
        except:
            pass
        
        print(f"Error sending invoice generation SMS: {str(e)}")
        return False

if __name__ == "__main__":
    generate_monthly_invoices() 