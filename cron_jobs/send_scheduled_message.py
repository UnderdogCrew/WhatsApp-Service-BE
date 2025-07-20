import os
import django
from datetime import datetime, timedelta

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from utils.database import MongoDB
from utils.whatsapp_message_data import send_message_data

# Define the target date ranges
target_days = {1, 2, 5, 10, 30}


def fetch_scheduled_messages():
    try:
        print(f"Starting invoice generation at {datetime.now()}")
        db = MongoDB()
        
        # Calculate date range for the previous month
        today = datetime.now()
        target_dates = [today + timedelta(days=day) for day in target_days]
        target_dates = [d.replace(hour=0, minute=0, second=0, microsecond=0) for d in target_dates]
        
        # Fetch all documents
        records = list(
            db.find_documents('whatsapp_schedule_message', {})
        )
        
        filtered_records = [record for record in records if 'date' in record and record['date'] in target_dates]

        for user in filtered_records:
            reg_number = ""
            model = ""
            policy = ""
            if "reg_number" in user:
                reg_number = user['reg_number']
                
            if "model" in user:
                model = user['model']

            if reg_number != "" and model != "":
                policy = f"{reg_number} ({model})"
            
            metadata = {
                "name" : user['name'],
                "company_name" : user['company_name'],
                "policy": policy,
                "date": user['date']
            }
            send_message_data(
                number=user['number'],
                template_name="insurance_policy",
                text=user['text'],
                image_url="",
                user_id=user['user_id'],
                metadata=metadata
            )

        print("Message send successfully......!!!!!!!")
        return True

    except Exception as e:
        print(f"Error generating monthly invoices: {str(e)}")
        return False

if __name__ == "__main__":
    fetch_scheduled_messages() 