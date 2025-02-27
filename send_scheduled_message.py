import os
import sys
import django
from datetime import datetime, timedelta
import os
current_path = os.path.abspath(os.getcwd())
base_path = os.path.dirname(current_path)  # This will give you /opt/whatsapp_service/WhatsApp-Service-BE
print(f"base_path: {base_path}")

# Set up Django environment
sys.path.append(base_path)  # Adjust this path accordingly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from utils.database import MongoDB
from utils.whatsapp_message_data import send_message_data

# Define the target date ranges
target_days = {1, 2, 5, 10, 30}


def fetch_scheduled_messages():
    try:
        # Set the desired hour and minute for execution
        scheduled_hour = 2  # Example: 10 AM
        scheduled_minute = 30  # Example: 0 minutes

        # Get the current time
        now = datetime.now()
        
        # Check if the current time matches the scheduled time
        if now.hour == scheduled_hour and now.minute == scheduled_minute:
            print(f"Starting invoice generation at {now}")
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
        else:
            print(f"Current time {now.strftime('%H:%M')} does not match scheduled time {scheduled_hour}:{scheduled_minute}. Skipping execution.")
            return False

    except Exception as e:
        print(f"Error generating monthly invoices: {str(e)}")
        return False

if __name__ == "__main__":
    fetch_scheduled_messages() 
    sys.exit(0)