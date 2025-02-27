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
import requests
import datetime
from UnderdogCrew.settings import API_KEY
import traceback
import pandas as pd

db = MongoDB()

'''
    API for login the user in portal
    request: phone number to send the otp on number
'''
API_TOKEN = API_KEY


def process_components(components, msg_data, image_url):
    result_list = []

    for component in components:
        if component['type'].upper() == "HEADER" and component.get('format') == "IMAGE":
            # Process HEADER with type IMAGE
            header_entry = {
                "type": "header",
                "parameters": [
                    {
                        "type": "image",
                        "image": {
                            "link": image_url
                        }
                    }
                ]
            }
            result_list.append(header_entry)

        elif component['type'].upper() == "BODY":
            # Check for body_text_named_params
            if 'body_text_named_params' in component.get('example', {}):
                # Process BODY with named parameters
                body_parameters = []
                for param in component['example']['body_text_named_params']:
                    value = msg_data.get(param['param_name'], param['example'])
                    # Convert Timestamp to string if necessary
                    if isinstance(value, pd.Timestamp):  # Assuming you are using pandas
                        value = value.strftime('%Y-%m-%d')  # Format as needed
                    body_parameters.append({
                        "type": "text",
                        "parameter_name": param['param_name'],
                        "text": value
                    })

                body_entry = {
                    "type": "body",
                    "parameters": body_parameters
                }
                result_list.append(body_entry)

            # Existing condition for body_text
            elif 'body_text' in component.get('example', {}):
                # Process BODY
                body_parameters = []
                print(component['example']['body_text'][0])
                for i, text in enumerate(component['example']['body_text'][0]):
                    # Convert Timestamp to string if necessary
                    if isinstance(text, pd.Timestamp):  # Assuming you are using pandas
                        text = text.strftime('%Y-%m-%d')  # Format as needed
                    body_parameters.append({
                        "type": "text",
                        "text": msg_data.get('Name') if i == 0 else text
                    })

                body_entry = {
                    "type": "body",
                    "parameters": body_parameters
                }
                result_list.append(body_entry)

    return result_list


def send_message_data(number, template_name, text, image_url, user_id, entry=None, metadata=None):
    try:
        url = "https://graph.facebook.com/v19.0/450885871446042/messages"
        template_url = f"https://graph.facebook.com/v21.0/236353759566806/message_templates?name={template_name}"
        headers = {
            'Authorization': f'Bearer {API_KEY}'
        }
        template_response = requests.request("GET", template_url, headers=headers)
        print(f"template response: {template_response.status_code}")
        if template_response.status_code != 200:
            return False
        
        template_data = template_response.json()
        template_components = template_data['data'][0]['components']
        template_text = template_components[0]['text'] if "text" in template_components[0] else ""
        category = template_data['data'][0]['category']
        language = template_data['data'][0]['language']

        if entry is not None:
            if "name" in entry:
                text = entry['name']
        
        company_name = ""
        if entry is not None:
            if "company_name" in entry:
                company_name = entry['company_name']
        
        reg_number = ""
        model = ""
        policy = ""
        if entry is not None:
            if "reg_number" in entry:
                reg_number = entry['reg_number']
            
            if "model" in entry:
                model = entry['model']

        if reg_number != "" and model != "":
            policy = f"{reg_number} ({model})"

        date = ""
        if entry is not None:
            if "date" in entry:
                date = entry['date']
        

        # Sending messages to specific numbers
        if text != "" and company_name != "" and policy != "" and date != "":
            msg_details = {
                "name": text,
                "company_name": company_name,
                "policy": policy,
                "date": date
            }
        elif metadata is not None:
            msg_details = metadata   
        else: 
            msg_details = {
                "Name": text
            }

        if template_text != "":
            template_text = template_text.replace("{{", "{")
            template_text = template_text.replace("}}", "}")
            template_text = template_text.format(**msg_details)

        components = process_components(template_components, msg_details, image_url)
        print(f"components: {template_text}")
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": f"91{number}",
            "type": "template",
            "template": {
                    "name": template_name,
                    "language": {
                        "code": language
                    },
                    "components": components
                }
            }
        )
        headers = {
            'Authorization': 'Bearer ' + API_TOKEN,
            'Content-Type': 'application/json'
        }
        print(f"Sending bulk message payload: {payload}")
        response = requests.post(url, headers=headers, data=payload)
        print(response.json())
        if response.status_code == 200:
            whatsapp_status_logs = {
                "number": f"91{number}",
                "message": template_text,
                "user_id": user_id,
                "price": 0.125 if category == "UTILITY" else 0.875,
                "id": response.json()['messages'][0]["id"],
                "message_status": response.json()['messages'][0]["message_status"],
                "created_at": int(datetime.datetime.now().timestamp()),
                "template_name": template_name
            }
            db.create_document('whatsapp_message_logs', whatsapp_status_logs)
        else:
            whatsapp_status_logs = {
                "number": f"91{number}",
                "message": template_text,
                "user_id": user_id,
                "price": 0,
                "id": "",
                "message_status": "error",
                "created_at": int(datetime.datetime.now().timestamp()),
                "template_name": template_name,
                "code": response.json()['error']['code'],
                "title": response.json()['error']['type'],
                "error_message": response.json()['error']['message'],
                "error_data": response.json()['error']['message'],
            }
            db.create_document('whatsapp_message_logs', whatsapp_status_logs)

        return True
    except Exception as e:
            # Print the error with line number and human-readable format
            error_message = f"Error occurred: {str(e)}\n"
            error_message += traceback.format_exc()
            print(error_message)  # Log the error for debugging
            return True

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