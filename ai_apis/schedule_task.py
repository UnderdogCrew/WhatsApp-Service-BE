import pandas as pd
from utils.database import MongoDB
from utils.whatsapp_message_data import send_message_data
import threading
import datetime
from bson import ObjectId


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
                "number": row_data['number'],
                "name": row_data['name'],
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
                "number": row_data['number'],
                "status": 1
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

            send_message_thread = threading.Thread(target=send_message_data, args=(row_data['number'], template_name, text, image_url, user_id, entry,  ),)
            send_message_thread.start()


        print("All data entries inserted successfully.")

        return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False