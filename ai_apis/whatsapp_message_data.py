import json
from utils.database import MongoDB
import requests
import datetime
from UnderdogCrew.settings import API_KEY, OPEN_AI_KEY
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

        elif component['type'].upper() == "BODY" and 'body_text' in component.get('example', {}):
            # Process BODY
            body_parameters = []
            print(component['example']['body_text'][0])
            for i, text in enumerate(component['example']['body_text'][0]):
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


def send_message_data(number, template_name, text, image_url, user_id):
    url = "https://graph.facebook.com/v19.0/450885871446042/messages"
    template_url = f"https://graph.facebook.com/v21.0/236353759566806/message_templates?name={template_name}"
    headers = {
        'Authorization': f'Bearer {API_KEY}'
    }
    template_response = requests.request("GET", template_url, headers=headers)
    print(template_response.status_code)
    if template_response.status_code != 200:
        return False
    
    template_data = template_response.json()
    template_components = template_data['data'][0]['components']

    # Sending messages to specific numbers
    msg_details = {
        "Name": text
    }

    components = process_components(template_components, msg_details, image_url)
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": f"91{number}",
        "type": "template",
        "template": {
                "name": template_name,
                "language": {
                    "code": "en"
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

    whatsapp_status_logs = {
        "number": f"91{number}",
        "message": text,
        "user_id": user_id,
        "id": response.json()['messages'][0]["id"],
        "message_status": response.json()['messages'][0]["message_status"],
        "created_at": int(datetime.datetime.now().timestamp()),
        "template_name": template_name
    }
    db.create_document('whatsapp_message_logs', whatsapp_status_logs)
    return True