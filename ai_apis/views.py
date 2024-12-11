# Create your views here.
import datetime

from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
import sys
import requests
import json
from UnderdogCrew.settings import API_KEY, OPEN_AI_KEY
import pandas as pd
import openai
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from utils.database import MongoDB


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


class SendMessage(APIView):
    @swagger_auto_schema(
        operation_description="Send a message via WhatsApp",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'text': openapi.Schema(type=openapi.TYPE_STRING, description='Text message to send'),
                'fileUrl': openapi.Schema(type=openapi.TYPE_STRING, description='URL of the Excel file'),
                'image_url': openapi.Schema(type=openapi.TYPE_STRING, description='Image URL (optional)'),
                'template_name': openapi.Schema(type=openapi.TYPE_STRING, description='Name of the template to send'),
                'message_type': openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description='Type of message to send (1 for bulk, 2 for single numbers)'
                ),
                'numbers': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description='Array of phone numbers for single messages (optional, required if message_type=2)'
                ),
            },
            required=['text', 'message_type', 'template_name']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            422: 'Unprocessable Entity',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            db = MongoDB()
            print(f"API_TOKEN: {API_TOKEN}")
            url = "https://graph.facebook.com/v19.0/450885871446042/messages"
            request_data = request.data
            template_name = request_data.get("template_name", None)
            # Validate required fields
            if not request_data:
                return JsonResponse({"message": "Request body is missing"}, safe=False, status=422)
            if "text" not in request_data:
                return JsonResponse({"message": "Text is missing"}, safe=False, status=422)
            if "fileUrl" not in request_data:
                return JsonResponse({"message": "File URL is missing"}, safe=False, status=422)
            if "message_type" not in request_data:
                return JsonResponse({"message": "Message type is missing"}, safe=False, status=422)
            if template_name is None:
                return JsonResponse({"message": "Template name is missing"}, safe=False, status=422)

            template_url = f"https://graph.facebook.com/v21.0/236353759566806/message_templates?name={template_name}"
            headers = {
                'Authorization': f'Bearer {API_KEY}'
            }
            template_response = requests.request("GET", template_url, headers=headers)
            print(template_response.status_code)
            if template_response.status_code != 200:
                return JsonResponse({"message": "Template is missing"}, safe=False, status=422)

            template_data = template_response.json()
            template_components = template_data['data'][0]['components']

            text = request_data['text']
            file_path = request_data['fileUrl']
            message_type = request_data['message_type']

            image_url = request_data.get('image_url', "")
            numbers = request_data.get('numbers', [])

            if message_type == 2 and not numbers:
                return JsonResponse(
                    {"message": "Numbers array is required for message_type 2"},
                    safe=False,
                    status=422
                )

            if message_type == 1 and file_path == "":
                return JsonResponse(
                    {"message": "file is required for message_type 1"},
                    safe=False,
                    status=422
                )

            if message_type == 1:
                # Bulk messaging using the Excel file
                msg_details = {
                    "Name": text
                }

                components = process_components(template_components, msg_details, image_url)
                df = pd.read_excel(file_path)
                for index, row in df.iterrows():
                    msg_data = row.to_dict()

                    payload = json.dumps({
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": f"91{msg_data['To Number']}",
                        "type": "template",
                        "template": {
                            "name": template_name,
                            "language": {
                                "code": "en"
                            },
                            "components": components
                        }
                    })
                    headers = {
                        'Authorization': 'Bearer ' + API_TOKEN,
                        'Content-Type': 'application/json'
                    }
                    print(f"Sending bulk message payload: {payload}")
                    response = requests.post(url, headers=headers, data=payload)
                    print(response.json())

                    whatsapp_status_logs = {
                        "number": f"91{msg_data['To Number']}",
                        "message": text,
                        "id": response.json()['messages'][0]["id"],
                        "message_status": response.json()['messages'][0]["message_status"],
                        "created_at": int(datetime.datetime.now().timestamp()),
                        "template_name": template_name
                    }
                    db.create_document('whatsapp_message_logs', whatsapp_status_logs)

            elif message_type == 2:
                # Sending messages to specific numbers
                msg_details = {
                    "Name": text
                }

                components = process_components(template_components, msg_details, image_url)
                for number in numbers:
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
                    })
                    headers = {
                        'Authorization': 'Bearer ' + API_TOKEN,
                        'Content-Type': 'application/json'
                    }
                    print(f"Sending single message payload: {payload}")
                    response = requests.post(url, headers=headers, data=payload)
                    print(response.json())
                    whatsapp_status_logs = {
                        "number": f"91{number}",
                        "message": text,
                        "id": response.json()['messages'][0]["id"],
                        "message_status": response.json()['messages'][0]["message_status"],
                        "created_at": int(datetime.datetime.now().timestamp()),
                        "template_name": template_name
                    }
                    db.create_document('whatsapp_message_logs', whatsapp_status_logs)

            return JsonResponse({"message": "Messages sent successfully"}, safe=False, status=200)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            return JsonResponse({"message": "Something went wrong"}, safe=False, status=500)


class FacebookWebhook(APIView):
    @swagger_auto_schema(
        operation_description="Webhook for Facebook messages",
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            db = MongoDB()
            data = request.data
            print(f"data: {data}")
            entry = data['entry']
            changes = entry[0]['changes']
            value = changes[0]['value']
            phone_number_id = value['metadata']['phone_number_id']
            statuses = value['statuses']

            # need to add the logs in database
            user = db.find_document('whatsapp_message_logs', {'id': statuses[0]['id']})
            if user:
                db.update_document(
                    'whatsapp_message_logs',
                    {'_id': user['_id']},
                    {
                        'message_status': statuses[0]['status'],
                        f"{statuses[0]['status']}_at": int(statuses[0]['timestamp'])
                    }
                )

            try:
                messages = value['messages'][0]['text']['body']
                from_number = value['messages'][0]['from']
                msg_type = value['messages'][0]['type']
            except:
                messages = ""
                from_number = ""
                msg_type = ""
            hub_challenge = "EAANWlQY0U2gBOxjQ1WIYomX99g9ZBarEiZBAftiZBYGVgvGWJ8OwZBwUdCEmgA1TZBZB9XT"
            if msg_type == "text":
                ## need to send message back
                payload = json.dumps(
                    {
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": from_number,
                        "type": "text",
                        "text": {
                            "preview_url": False,
                            "body": "response"
                        }
                    }
                )
                print("from_number", from_number)
                headers = {
                    'Authorization': 'Bearer ' + API_TOKEN,
                    'Content-Type': 'application/json',
                    'Cookie': 'ps_l=0; ps_n=0'
                }
                url = "https://graph.facebook.com/v19.0/450885871446042/messages"
                response = requests.request("POST", url, headers=headers, data=payload)
                print(response.json())

            response_data = {
                "message": "Message send successfully",
            }
            return HttpResponse(hub_challenge)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong",
                "token": "EAANWlQY0U2gBOxjQ1WIYomX99g9ZBarEiZBAftiZBYGVgvGWJ8OwZBwUdCEmgA1TZBZB9XT"
            }
            return JsonResponse("EAANWlQY0U2gBOxjQ1WIYomX99g9ZBarEiZBAftiZBYGVgvGWJ8OwZBwUdCEmgA1TZBZB9XT", safe=False,
                                status=500)

    @swagger_auto_schema(
        operation_description="Verify the webhook",
        responses={
            200: openapi.Response('Challenge response'),
            500: 'Internal Server Error'
        }
    )
    def get(self, request):
        try:
            data = request.GET.get("hub.verify_token")
            challenge = request.GET.get("hub.challenge")
            hub_challenge = data
            print(f"challenge {challenge}")
            return HttpResponse(challenge, content_type="text/plain", status=200)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong",
                "token": "EAANWlQY0U2gBOxjQ1WIYomX99g9ZBarEiZBAftiZBYGVgvGWJ8OwZBwUdCEmgA1TZBZB9XT"
            }
            return JsonResponse("EAANWlQY0U2gBOxjQ1WIYomX99g9ZBarEiZBAftiZBYGVgvGWJ8OwZBwUdCEmgA1TZBZB9XT", safe=False,
                                status=500)



class ImageGeneration(APIView):
    @swagger_auto_schema(
        operation_description="Generate an image from text",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'text': openapi.Schema(type=openapi.TYPE_STRING, description='Text prompt for image generation'),
            },
            required=['text']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'url': openapi.Schema(type=openapi.TYPE_STRING, description='Generated image URL'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            422: 'Unprocessable Entity',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            request_data = request.data
            if len(request_data) == 0:
                response_data = {
                    "message": "request body is missing",
                }
                return JsonResponse(response_data, safe=False, status=422)
            elif "text" not in request_data:
                response_data = {
                    "message": "text is missing",
                }
                return JsonResponse(response_data, safe=False, status=422)
            else:
                text = request_data['text']
                openai.api_key = OPEN_AI_KEY
                response = openai.images.generate(
                    model="dall-e-3",
                    prompt=text,
                    size="1024x1024",
                    quality="hd",
                    n=1,
                )
                image_url = response.data[0].url
                response_data = {
                    "url": image_url,
                    "message": "Data Found"
                }
                return JsonResponse(response_data, safe=False, status=200)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


class TextGeneration(APIView):
    @swagger_auto_schema(
        operation_description="Generate text based on input",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'text': openapi.Schema(type=openapi.TYPE_STRING, description='Input text for generation'),
                'textType': openapi.Schema(type=openapi.TYPE_INTEGER, description='Type of text transformation (optional)'),
            },
            required=['text']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'text': openapi.Schema(type=openapi.TYPE_STRING, description='Generated text'),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            422: 'Unprocessable Entity',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            request_data = request.data
            if len(request_data) == 0:
                response_data = {
                    "message": "request body is missing",
                }
                return JsonResponse(response_data, safe=False, status=422)
            elif "text" not in request_data:
                response_data = {
                    "message": "text is missing",
                }
                return JsonResponse(response_data, safe=False, status=422)
            else:
                text = request_data['text']
                text_type = request_data['textType'] if "textType" in request_data else 1
                openai_api_key = OPEN_AI_KEY
                headers = {
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                }

                if text_type == 1:
                    pass
                elif text_type == 2:
                    text = text + " and make it formal"
                elif text_type == 3:
                    text = text + " and make it Fun"
                elif text_type == 4:
                    text = text + " translate the text to tamil"
                elif text_type == 5:
                    text = text + " translate the text to hindi"
                elif text_type == 6:
                    text = text + " rewrite the above text"
                elif text_type == 7:
                    text = text + " make the above text formal"
                elif text_type == 8:
                    text = text + " make the above text fun"
                else:
                    pass

                text = text + "\n Return only message without any explanation"

                data = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": text}
                    ]
                }

                response = requests.post("https://api.openai.com/v1/chat/completions", json=data, headers=headers)
                print(response.json())
                response_text = response.json()['choices'][0]['message']['content']
                if text_type == 1:
                    if ":\n" in response_text:
                        response_text = response_text.split(":\n")[1]
                    if '\" \'' in response_text:
                        response_text = response_text.split('\" \'')[0]
                    if '\n\n' in response_text:
                        response_text = response_text.split('\n\n')[0]
                    if " (" in response_text:
                        response_text = response_text.split(" (")[0]
                    if ": " in response_text:
                        response_text = response_text.split(": ")[1]

                    response_text = response_text.replace("\"", "")
                    response_text.replace("\n", "")

                if "Hindi:" in response_text and text_type == 5:
                    response_text = response_text.split("Hindi:")[1]

                response_data = {
                    "text": response_text,
                    "message": "Data Found"
                }
                return JsonResponse(response_data, safe=False, status=200)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)