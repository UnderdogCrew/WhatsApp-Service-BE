import pandas as pd
from utils.database import MongoDB
from utils.whatsapp_message_data import send_message_data
import threading


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