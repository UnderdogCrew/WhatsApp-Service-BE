import pandas as pd
from utils.database import MongoDB
from utils.whatsapp_message_data import send_message_data
import threading
import datetime
from bson import ObjectId
import calendar


def schedule_message(file_path, user_id, image_url, template_name, text):
    db = MongoDB()
    try:
        # Step 1: Read data from the sheet
        data = pd.read_excel(file_path)  # Adjust the path and file type as needed

        # Step 2: Loop through each row in the DataFrame
        for index, row in data.iterrows():
            # Create a dictionary for the current entry with additional fields
            row_data = row.to_dict()
            row_data['user_id'] = user_id
            row_data['image_url'] = image_url
            row_data['template_name'] = template_name if row_data['template_name'] is None else row_data['template_name']
            row_data['text'] = text

            ## we need to add the numbers and name as a customer
            customer_details = {
                "number": int(row_data['number']),
                "name": row_data['name'],
                "user_id": user_id,
                "insurance_type": row_data['insurance_type'] if "insurance_type" in row_data else "",
                "model": row_data['model'] if "model" in row_data else "",
                "reg_number": row_data['reg_number'] if "reg_number" in row_data else "",
                "policy_type": row_data['policy_type'] if "policy_type" in row_data else "",
                "company_name": row_data['company_name'] if "company_name" in row_data else "",
                "date": row_data['date'] if "date" in row_data else "",
                "status": 1,
                "created_at": datetime.datetime.now()
            }
            customer_query = {
                "number": int(row_data['number']),
                "status": 1,
                "user_id": user_id
            }
            customer_data = db.find_document(collection_name='customers', query=customer_query)
            if customer_data is not None:
                update_data = {
                    "name": row_data['name'],
                    "insurance_type": row_data['insurance_type'] if "insurance_type" in row_data else "",
                    "model": row_data['model'] if "model" in row_data else "",
                    "reg_number": row_data['reg_number'] if "reg_number" in row_data else "",
                    "policy_type": row_data['policy_type'] if "policy_type" in row_data else "",
                    "company_name": row_data['company_name'] if "company_name" in row_data else "",
                    "date": row_data['date'] if "date" in row_data else "",
                }
                db.update_document(collection_name="customers", query={"_id": ObjectId(customer_data['_id'])}, update_data=update_data)
            else:
                db.create_document('customers', customer_details)

            entry = row_data

            # Insert the current entry into MongoDB
            db.create_document('whatsapp_schedule_message', entry)

            start_date = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            currnt_month = start_date.month
            current_month = start_date.month
            current_year = start_date.year

            # Get the last day of the current month
            last_day = calendar.monthrange(current_year, current_month)[1]

            # Construct the last datetime of the month
            end_of_month = datetime.datetime(current_year, current_month, last_day, 23, 59, 59)
            date_to_check = entry['date']
            # print(entry['date'])
            if isinstance(date_to_check, str):
                date_to_check = datetime.datetime.strptime(date_to_check, "%Y-%m-%d %H:%M:%S")

            if start_date <= date_to_check <= end_of_month:
                send_message_thread = threading.Thread(target=send_message_data, args=(row_data['number'], template_name, text, image_url, user_id, entry,  ),)
                send_message_thread.start()


        print("All data entries inserted successfully.")

        return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False