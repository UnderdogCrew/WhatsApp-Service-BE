import json
from utils.database import MongoDB
import requests
import datetime
from UnderdogCrew.settings import API_KEY, OPEN_AI_KEY, GLAM_API_KEY
import traceback
import pandas as pd
import os
import sys
import django
from bson import ObjectId
import time

current_path = os.path.abspath(os.getcwd())
base_path = os.path.dirname(current_path)  # This will give you /opt/whatsapp_service/WhatsApp-Service-BE

# Set up Django environment
sys.path.append(base_path)  # Adjust this path accordingly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

db = MongoDB()

'''
    API for login the user in portal
    request: phone number to send the otp on number
'''
API_TOKEN = API_KEY


def process_components(components, msg_data, image_url, latitude=None, longitude=None, location_name=None, address=None):
    result_list = []

    for component in components:
        if component['type'].upper() == "HEADER" and component.get('format') == "IMAGE":
            # Process HEADER with type IMAGE
            if image_url != "":
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
        elif component['type'].upper() == "HEADER" and component.get('format') == "VIDEO":
            # Process HEADER with type VIDEO
            if image_url != "":
                header_entry = {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "video",
                            "video": {
                                "link": image_url
                            }
                        }
                    ]
                }
                result_list.append(header_entry)
        elif component['type'].upper() == "HEADER" and component.get('format') == "DOCUMENT":
            # Process HEADER with type DOCUMENT
            if image_url != "":
                header_entry = {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": image_url
                            }
                        }
                    ]
                }
                result_list.append(header_entry)
        elif component['type'].upper() == "HEADER" and component.get('format') == "LOCATION":
            # Process HEADER with type DOCUMENT
            if latitude is not None and longitude is not None:
                header_entry = {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "location",
                            "location": {
                                "latitude": latitude,
                                "longitude": longitude,
                                "name": location_name,
                                "address": address
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
            # elif "text" in component:
            #     # Process BODY
            #     body_parameters = []
            #     text = component['text']
            #     # Convert Timestamp to string if necessary
            #     if isinstance(text, pd.Timestamp):  # Assuming you are using pandas
            #         text = text.strftime('%Y-%m-%d')  # Format as needed
            #     body_parameters.append({
            #         "type": "text",
            #         "text": text
            #     })

            #     body_entry = {
            #         "type": "body",
            #         "parameters": body_parameters
            #     }
            #     result_list.append(body_entry)
            
        elif component['type'].upper() == "BUTTONS":
            # Check for body_text_named_params
            for buttons in component['buttons']:
                # Process BODY with named parameters
                body_parameters = []
                if buttons['type'] == "URL":
                    value = buttons.get("text", "")
                    if "example" in buttons:
                        body_parameters.append({
                            "type": "text",
                            "text": "/billing"
                        })
                    else:
                        body_parameters.append({
                            "type": "text",
                            "text": buttons['url']
                        })

                if "example" in buttons:
                    body_entry = {
                        "type": "BUTTON",
                        "sub_type": "url",
                        "index": 0,
                        "parameters": body_parameters
                    }
                    result_list.append(body_entry)

    return result_list


def send_message_data(number, template_name, text, image_url, user_id, entry=None, metadata=None, latitude=None, longitude=None, location_name=None, address=None):
    try:
        
        user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})

        if user_info is not None:
            business_id = user_info['business_id']
        else:
            business_id = "450885871446042"

        url = f"https://graph.facebook.com/v19.0/{business_id}/messages"
        if user_id == "67e6a22d44e08602e5c1e91c":
            template_url = f"https://graph.facebook.com/v21.0/1156861725908077/message_templates?name={template_name}"
            API_TOKEN = GLAM_API_KEY
        else:
            template_url = f"https://graph.facebook.com/v21.0/236353759566806/message_templates?name={template_name}"
            API_TOKEN = API_KEY
        headers = {
            'Authorization': f'Bearer {API_TOKEN}'
        }
        template_response = requests.request("GET", template_url, headers=headers)
        print(f"template response: {template_response.status_code}")
        if template_response.status_code != 200:
            return False
        
        template_data = template_response.json()
        template_components = template_data['data'][0]['components']

        # Check if there are any BUTTONS in the components
        has_buttons = any(component['type'].upper() == "BUTTONS" for component in template_components)

        template_text = ""
        for components in template_components:
            if components['type'] == "BODY":
                template_text = components['text']
        print(f"template_text: {template_text}")
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

        if reg_number != "" and model != "" and reg_number is not None:
            policy = f"{reg_number} ({model})"
        else:
            policy = f"{model}"

        date = ""
        if entry is not None:
            if "date" in entry:
                # Convert date to string format if it's a datetime object
                if isinstance(entry['date'], datetime.datetime):
                    try:
                        date = entry['date'].strftime("%d-%m-%Y")  # Convert to string
                    except:
                        date = entry['date']
                else:
                    date = entry['date']  # Assume it's already a string
        

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
        
        print(f"template text: {template_text}")

        components = process_components(template_components, msg_details, image_url, latitude=latitude, longitude=longitude, location_name=location_name, address=address)
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
        
        if category != "UTILITY":
            time.sleep(7)
        
        response = requests.post(url, headers=headers, data=payload)
        print(f"Meta response: {response.status_code}")
        if response.status_code == 200:
            whatsapp_status_logs = {
                "number": f"91{number}",
                "message": template_text,
                "user_id": user_id,
                "price": 0.125 if category == "UTILITY" else 0.875,
                "id": response.json()['messages'][0]["id"],
                "message_status": response.json()['messages'][0]["message_status"] if "message_status" in response.json()['messages'][0] else "sent",
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now(),
                "template_name": template_name
            }
            db.create_document('whatsapp_message_logs', whatsapp_status_logs)
        else:
            print(f"Meta response: {response.json()}")
            whatsapp_status_logs = {
                "number": f"91{number}",
                "message": template_text,
                "user_id": user_id,
                "price": 0,
                "id": "",
                "message_status": "error",
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now(),
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