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
import re

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


def process_components(components, msg_data, image_url, latitude=None, longitude=None, location_name=None, address=None, template_text=None):
    result_list = []
    print(f"msg_data: {msg_data}")
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

        elif component['type'].upper() == "FOOTER":
            body_entry = {
                "type": "footer",
                "parameters": [
                    {
                        "type": "text",
                        "text": component['text']
                    }
                ]
            }
            result_list.append(body_entry)

        elif component['type'].upper() == "BODY":
            # Check for body_text_named_params
            if "example" in component:
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
                elif 'body_text' in component.get('example', {}) or "text" in component:
                    # Process BODY
                    body_parameters = []
                    if len(msg_data) == 0:
                        body_parameters.append({
                            "type": "text",
                            "text": template_text
                        })
                    else:
                        for param in range(len(component['example']['body_text'][0])):
                            value = msg_data.get(str(param+1))
                            # Convert Timestamp to string if necessary
                            if isinstance(value, pd.Timestamp):  # Assuming you are using pandas
                                value = value.strftime('%Y-%m-%d')  # Format as needed
                            body_parameters.append({
                                "type": "text",
                                "text": value
                            })
                    body_entry = {
                        "type": "body",
                        "parameters": body_parameters
                    }
                    result_list.append(body_entry)
            # else:
            #     if "text" in component:
            #         body_entry = {
            #             "type": "body",
            #             "parameters": [
            #                 {
            #                     "type": "text",
            #                     "text": template_text
            #                 }
            #             ]
            #         }
            #         result_list.append(body_entry)

        elif component['type'].upper() == "BUTTONS":
            # Check for body_text_named_params
            for button_index in range(len(component['buttons'])):
                # Process BODY with named parameters
                body_parameters = []
                buttons = component['buttons'][button_index]
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
                
                if buttons['type'] == "QUICK_REPLY":
                    quick_reply = {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": str(button_index),
                        "parameters": [
                            {
                                "type": "payload",
                                "payload": buttons['text']
                            }
                        ]
                    }
                    result_list.append(quick_reply)
                
                # if buttons['type'] == "PHONE_NUMBER":
                #     quick_reply = {
                #         "type": "button",
                #         "index": str(button_index),
                #         "parameters": [
                #             {
                #                 "type": "phone_number",
                #                 "phone_number": buttons['phone_number']
                #             }
                #         ]
                #     }
                #     result_list.append(quick_reply)
                
                if buttons['type'] == "COPY_CODE":
                    copy_code = {
                        "type": "button",
                        "sub_type": "copy_code",
                        "index": str(button_index),
                        "parameters": [
                            {
                                "type": "coupon_code",
                                "coupon_code": buttons['example'][0]
                            }
                        ]
                    }
                    result_list.append(copy_code)
                

                if buttons['type'] == "FLOW":
                    flow_json = {
                        "type": "button",
                        "sub_type": "flow",
                        "index": str(button_index),
                        "parameters": [
                            {
                                "type": "ACTION",
                                "action": {
                                    "flow_token": "unused",
                                    # "flow_id": buttons['flow_id'],
                                    # "flow_action": buttons['flow_action'],
                                    # "navigate_screen": buttons['navigate_screen']
                                }
                            }
                        ]
                    }
                    result_list.append(flow_json)

                if "example" in buttons and len(body_parameters) > 0:
                    body_entry = {
                        "type": "BUTTON",
                        "sub_type": "url",
                        "index": 0,
                        "parameters": body_parameters
                    }
                    result_list.append(body_entry)

    return result_list


def send_message_data(
        number,
        template_name,
        text, image_url,
        user_id,
        entry=None,
        metadata=None,
        latitude=None,
        longitude=None,
        location_name=None,
        address=None,
        params_fallback_value=None
    ):
    try:
        
        user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})
        user_credit = 0

        if user_info is not None:
            business_id = user_info['business_id']
            phone_number_id = user_info['phone_number_id']
            waba_id = user_info['waba_id']
            api_key = user_info['api_key']
            user_credit = user_info['default_credit']
        
        url = f"https://graph.facebook.com/v23.0/{phone_number_id}/messages"
        template_url = f"https://graph.facebook.com/v21.0/{waba_id}/message_templates?name={template_name}"
        API_TOKEN = api_key
        
        headers = {
            'Authorization': f'Bearer {API_TOKEN}'
        }
        template_response = requests.request("GET", template_url, headers=headers)
        if template_response.status_code != 200:
            return False
        
        template_data = template_response.json()
        # Get the object with name == "insurance_policy"
        template_result = next((item for item in template_data['data'] if item["name"] == template_name), None)
        if template_result is None:
            template_components = template_data['data'][0]['components']
        else:
            template_components = template_result['components']

        # Check if there are any BUTTONS in the components
        has_buttons = any(component['type'].upper() == "BUTTONS" for component in template_components)

        template_text = ""
        original_text = ""
        for components in template_components:
            if components['type'] == "BODY":
                template_text = components['text']
                original_text = components['text']
        category = template_data['data'][0]['category'] if template_result is None else template_result['category']
        language = template_data['data'][0]['language'] if template_result is None else template_result['language']
        print(f"template language ==> {language}")

        if entry is not None:
            if "name" in entry:
                text = entry['name']
                if entry['name'] == "$Name":
                    customer_details = db.find_document(
                        collection_name="customers",
                        query={
                            "number": number
                        }
                    )
                    if customer_details is not None:
                        text = customer_details['name']
                    else:
                        if params_fallback_value is not None:
                            if "name" in params_fallback_value:
                                text = params_fallback_value['name']
                            else:
                                pass
                    metadata['name'] = text
                else:
                    pass
        
        send_metadata = {}
        if metadata is not None:
            for key, value in metadata.items():
                if value == "$Name":
                    customer_details = db.find_document(
                            collection_name="customers",
                            query={
                                "number": number
                            }
                        )
                    if customer_details is None:
                        try:
                            customer_details = db.find_document(
                                collection_name="customers",
                                query={
                                    "number": int(number)
                                }
                            )
                        except:
                            pass

                    if customer_details is not None:
                        text = customer_details['name']
                    else:
                        if params_fallback_value is not None:
                            if "name" in params_fallback_value:
                                text = params_fallback_value['name']
                            else:
                                pass
                    send_metadata[key] = text
                else:
                    send_metadata[key] = value

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
        elif entry is not None:
            msg_details = entry
        elif metadata is not None:
            msg_details = send_metadata   
        else: 
            msg_details = {
                "Name": text
            }

        if template_text != "":
            template_text = template_text.replace("{{", "{")
            template_text = template_text.replace("}}", "}")
            try:
                for key, val in msg_details.items():
                    template_text = template_text.replace(f'{{{key}}}', val)
            except:
                # Convert keys to a list in order: 1, 2, 3, ...
                pass
        

        if original_text != "":
            original_text = original_text.replace("{{", "{")
            original_text = original_text.replace("}}", "}")
            try:
                for key, val in msg_details.items():
                    print(key)
                    original_text = original_text.replace(f'{{{key}}}', val)
            except:
                print("Error while passing the value in variable")
                # Convert keys to a list in order: 1, 2, 3, ...
                pass
        
        
        # 1. remove hard TABs
        template_text = template_text.replace("\t", "")
        template_text = template_text.replace("\n\n", "")

        # 2. collapse runs of ≥5 spaces (rule: max 4)
        template_text = re.sub(r" {5,}", "    ", template_text)

        # 3. **escape EVERY newline (CR, LF, CRLF)**
        template_text = template_text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
        print(template_text)
        components = process_components(
            template_components,
            msg_details,
            image_url,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            address=address,
            template_text=template_text
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": f"{number}",
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language
                },
                "components": components
            }
        }
        headers = {
            'Authorization': 'Bearer ' + API_TOKEN,
            'Content-Type': 'application/json'
        }
        print(f"Sending bulk message payload: \n {payload}")
        response = requests.post(url, headers=headers, json=payload)
        print(f"Meta response: {response.status_code}")
        print(f"Meta response: {response.text}")
        try:
            phone_number = number.split("+")[-1]
        except:
            phone_number = str(number)
        if response.status_code == 200:
            whatsapp_status_logs = {
                "number": f"91{phone_number}" if "91" not in phone_number else f"{phone_number}",
                "message": original_text,
                "user_id": user_id,
                "image_url": image_url,
                "price": 0.125 if category == "UTILITY" else 0.875,
                "id": response.json()['messages'][0]["id"],
                "message_status": response.json()['messages'][0]["message_status"] if "message_status" in response.json()['messages'][0] else "sent",
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now(),
                "template_name": template_name,
                "metadata": msg_details,
            }
            db.create_document('whatsapp_message_logs', whatsapp_status_logs)
            db.update_document(
                collection_name="users",
                query={"_id": ObjectId(user_id)},
                update_data={
                    "default_credit": user_credit - 0.125 if category == "UTILITY" else user_credit - 0.875
                }
            )

        else:
            whatsapp_status_logs = {
                "number": f"91{phone_number}" if "91" not in phone_number else f"{phone_number}",
                "message": original_text,
                "user_id": user_id,
                "price": 0,
                "id": "",
                "message_status": "error",
                "image_url": image_url,
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now(),
                "template_name": template_name,
                "code": response.json()['error']['code'],
                "title": response.json()['error']['type'],
                "error_message": response.json()['error']['message'],
                "error_data": response.json()['error']['message'],
                "metadata": msg_details,
            }
            db.create_document('whatsapp_message_logs', whatsapp_status_logs)

        return True
    except Exception as e:
            # Print the error with line number and human-readable format
            error_message = f"Error occurred: {str(e)}\n"
            error_message += traceback.format_exc()
            print(error_message)  # Log the error for debugging
            return True