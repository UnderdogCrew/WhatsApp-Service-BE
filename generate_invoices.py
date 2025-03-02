import os
import django
from datetime import datetime, timedelta
from django.utils import timezone
import pytz
import calendar

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from utils.database import MongoDB
from utils.auth import current_dollar_price

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

        print("Monthly invoice generation completed successfully")
        return True

    except Exception as e:
        print(f"Error generating monthly invoices: {str(e)}")
        return False

if __name__ == "__main__":
    generate_monthly_invoices() 