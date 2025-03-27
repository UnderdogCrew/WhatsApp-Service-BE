import os
import sys
import django
from datetime import datetime, timedelta
import os
import traceback

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
target_days = {0, 1, 2, 5, 10}


def fetch_scheduled_messages():
    try:
        db = MongoDB()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        final_record = []
        
        # Fetch all documents
        records = list(
            db.find_documents('whatsapp_schedule_message', query={"user_id": "67c1cf4c2763ce36e17d145e"})
        )

        for record in records:
            if isinstance(record['date'], str):
                try:
                    date = datetime.strptime(record['date'], "%d/%m/%y")
                except:
                    try:
                        date = datetime.strptime(record['date'], "%m/%d/%y")
                    except:
                        continue
            else:
                date = record['date']
            record['date'] = date.replace(hour=0, minute=0, second=0, microsecond=0)
            final_record.append(record)

        # Determine records to send messages to
        if today.day == 1:
            # Current month: first day and last day
            first_day_this_month = today.replace(day=1)
            if today.month == 12:
                last_day_this_month = today.replace(month=12, day=31)
            else:
                next_month = today.replace(day=28) + timedelta(days=4)  # always gives next month
                last_day_this_month = next_month.replace(day=1) - timedelta(days=1)

            filtered_records = [
                record for record in final_record
                if first_day_this_month <= record['date'] <= last_day_this_month
            ]
        else:
            # Use target_days logic
            target_dates = [today + timedelta(days=day) for day in target_days]
            target_dates = [d.replace(hour=0, minute=0, second=0, microsecond=0) for d in target_dates]

            filtered_records = [record for record in final_record if record['date'] in target_dates]

        unique_records = {}
        for record in filtered_records:
            number = record['number']
            if number not in unique_records:
                unique_records[number] = record

        filtered_records = list(unique_records.values())

        print(f"filtered_records: {filtered_records}")

        # Send messages
        for user in filtered_records:
            reg_number = user.get('reg_number', '')
            model = user.get('model', '')
            policy = f"{reg_number} ({model})" if reg_number and model else model

            metadata = {
                "name": user['name'],
                "company_name": user['company_name'],
                "policy": policy,
                "date": user['date'].strftime("%d-%m-%Y")
            }
            send_message_data(
                number=user['number'],
                template_name="insurance_policy",
                text=user.get('text', ''),
                image_url="",
                user_id=user['user_id'],
                metadata=metadata
            )

        print("Message send successfully......!!!!!!!")
        return True

    except Exception as e:
        tb = traceback.extract_tb(sys.exc_info()[2])[-1]  # Get last traceback frame
        line_number = tb.lineno
        print(f"Error generating scheduled messages on line {line_number}: {str(e)}")
        return False


if __name__ == "__main__":
    fetch_scheduled_messages() 
    sys.exit(0)