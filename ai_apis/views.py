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
import pytz
from ai_apis.schedule_task import schedule_message
import threading


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
                "schedule_type": openapi.Schema(type=openapi.TYPE_INTEGER, description='Type of the message which needs to send message for instante or schedule(1 for instante and 2 for schedule)'),
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
            user_id = "1"
            print(f"API_TOKEN: {API_TOKEN}")
            url = "https://graph.facebook.com/v19.0/450885871446042/messages"
            request_data = request.data
            template_name = request_data.get("template_name", None)
            # Validate required fields
            if not request_data:
                return JsonResponse({"message": "Request body is missing"}, safe=False, status=422)
            if "text" not in request_data:
                return JsonResponse({"message": "Text is missing"}, safe=False, status=422)
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
            schedule_type = request_data['schedule_type'] if "schedule_type" in request_data else 1
            file_path = request_data['fileUrl'] if "fileUrl" in request_data else ""
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

            if schedule_type == 2:
                threading.Thread(target=schedule_message, args=(file_path, user_id, ),)
                return JsonResponse(
                    {"message": "Message scheduled successfully"},
                    safe=False,
                    status=200
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
                        "user_id": user_id,
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
                        "user_id": user_id,
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
                code = 0
                title = ""
                message = ""
                error_data = ""
                try:
                    errors = statuses[0]['errors'][0]
                    code = errors['code']
                    title = errors['title']
                    message = errors['message']
                    error_data = errors['error_data']['details']
                except:
                    pass

                db.update_document(
                    'whatsapp_message_logs',
                    {'_id': user['_id']},
                    {
                        'message_status': statuses[0]['status'],
                        f"{statuses[0]['status']}_at": int(statuses[0]['timestamp']),
                        "code": code,
                        "title": title,
                        "error_message": message,
                        "error_data": error_data,
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
            db = MongoDB()
            user_id = "1"
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

                image_generation_logs = {
                    "message": text,
                    "user_id": user_id,
                    "created_at": int(datetime.datetime.now().timestamp()),
                    "image_url": image_url
                }
                db.create_document('image_generation_logs', image_generation_logs)

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
            db = MongoDB()
            user_id = "1"
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

                text_generation_logs = {
                    "message": text,
                    "user_id": user_id,
                    "created_at": int(datetime.datetime.now().timestamp()),
                    "response": response_text,
                    "input_token": len(text),
                    "output_token": len(response_text),
                }
                db.create_document('text_generation_logs', text_generation_logs)

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



class UserDashboard(APIView):
    @swagger_auto_schema(
        operation_description="Fetch user dashboard data",
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date for filtering data (optional, format: YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date for filtering data (optional, format: YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False,
            )
        ],
        responses={
            200: openapi.Response(
                "Success",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "data": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                )
            ),
            401: "Unauthorized",
            500: "Internal Server Error",
        }
    )
    def get(self, request):
        try:
            user_id = "1"
            # Parse optional query parameters
            start_date = request.query_params.get("start_date", None)
            end_date = request.query_params.get("end_date", None)

            # Validate and process date formats
            if start_date:
                try:
                    start_date_gmt = datetime.datetime.strptime(start_date, "%Y-%m-%d")

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    start_date = kolkata_timezone.localize(start_date_gmt)
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid start_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if end_date:
                try:
                    end_date_gmt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
                    end_date_gmt = end_date_gmt.replace(hour=23, minute=59, second=59, microsecond=59)

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    end_date = kolkata_timezone.localize(end_date_gmt)
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid end_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # # Validate Authorization header
            # auth_token = request.headers.get("Authorization")
            # if not auth_token:
            #     return Response(
            #         {"message": "Authorization header missing"},
            #         status=status.HTTP_401_UNAUTHORIZED,
            #     )

            # Connect to the database
            db = MongoDB()

            # Build query filter based on dates
            query_filter = {"user_id": user_id}
            text_filter = {"user_id": user_id}
            if start_date:
                query_filter["created_at"] = {"$gte": start_date}
                text_filter["created_at"] = {"$gte": start_date}
            if end_date:
                if "created_at" in query_filter:
                    query_filter["created_at"]["$lte"] = end_date
                    text_filter["created_at"]["$lte"] = end_date
                else:
                    query_filter["created_at"] = {"$lte": end_date}
                    text_filter["created_at"] = {"$lte": end_date}
            print(f"text filter: {text_filter}")
            # Fetch data from database
            total_message = len(db.find_documents("whatsapp_message_logs", query_filter))
            query_filter['status'] = "delivered"
            total_message_received = len(db.find_documents("whatsapp_message_logs", query_filter))
            text_generation_logs = len(db.find_documents("text_generation_logs", text_filter))
            image_generation_logs = len(db.find_documents("image_generation_logs", text_filter))

            response_data = {
                "total_message": total_message,
                "total_message_received": total_message_received,
                "text_generation_logs": text_generation_logs,
                "image_generation_logs": image_generation_logs
            }

            return JsonResponse(response_data, status=status.HTTP_200_OK)

        except Exception as ex:
            print(f"Error: {ex}")
            return JsonResponse({"message": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UserMessageLogs(APIView):
    @swagger_auto_schema(
        operation_description="Fetch user message logs",
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date for filtering data (optional, format: YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date for filtering data (optional, format: YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                "skip",
                openapi.IN_QUERY,
                description="skip the data",
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                "limit",
                openapi.IN_QUERY,
                description="limit the data",
                type=openapi.TYPE_INTEGER,
                required=False,
            )
        ],
        responses={
            200: openapi.Response(
                "Success",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "data": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                )
            ),
            401: "Unauthorized",
            500: "Internal Server Error",
        }
    )
    def get(self, request):
        try:
            user_id = "1"
            # Parse optional query parameters
            start_date = request.query_params.get("start_date", None)
            end_date = request.query_params.get("end_date", None)
            skip = int(request.query_params.get("skip", 0))
            limit = int(request.query_params.get("limit", 20))

            # Validate and process date formats
            if start_date:
                try:
                    start_date_gmt = datetime.datetime.strptime(start_date, "%Y-%m-%d")

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    start_date = kolkata_timezone.localize(start_date_gmt)
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid start_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if end_date:
                try:
                    end_date_gmt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
                    end_date_gmt = end_date_gmt.replace(hour=23, minute=59, second=59, microsecond=59)

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    end_date = kolkata_timezone.localize(end_date_gmt)
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid end_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # # Validate Authorization header
            # auth_token = request.headers.get("Authorization")
            # if not auth_token:
            #     return Response(
            #         {"message": "Authorization header missing"},
            #         status=status.HTTP_401_UNAUTHORIZED,
            #     )

            # Connect to the database
            db = MongoDB()

            # Build query filter based on dates
            query_filter = {"user_id": user_id}
            text_filter = {"user_id": user_id}
            if start_date:
                query_filter["created_at"] = {"$gte": start_date}
                text_filter["created_at"] = {"$gte": start_date}
            if end_date:
                if "created_at" in query_filter:
                    query_filter["created_at"]["$lte"] = end_date
                    text_filter["created_at"]["$lte"] = end_date
                else:
                    query_filter["created_at"] = {"$lte": end_date}
                    text_filter["created_at"] = {"$lte": end_date}
            print(f"text filter: {text_filter}")
            # Fetch data from database
            total_message = db.find_documents("whatsapp_message_logs", query_filter).sort("_id", -1).skip(skip).limit(limit)
            total_message_count = len(db.find_documents("whatsapp_message_logs", query_filter))

            message_list = []
            for _message in total_message:
                # Convert ISO string to datetime object
                dt_obj = datetime.strptime(_message['created_at'], "%Y-%m-%dT%H:%M:%S.%f")
                # Convert to a human-readable format
                human_readable = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                
                try:
                    updated_dt_obj = datetime.strptime(_message['updated_at'], "%Y-%m-%dT%H:%M:%S.%f")
                    # Convert to a human-readable format
                    updated_at_human_readable = updated_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    updated_at_human_readable = ""

                try:
                    # Convert to a datetime object
                    sent_dt_obj = datetime.utcfromtimestamp(_message['sent_at'])

                    # Format it into a readable format
                    sent_dt_readable = sent_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    sent_dt_readable = ""
                
                try:
                    # Convert to a datetime object
                    delivered_at_obj = datetime.utcfromtimestamp(_message['delivered_at'])

                    # Format it into a readable format
                    delivered_at_readable = delivered_at_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    delivered_at_readable = ""


                try:
                    # Convert to a datetime object
                    failed_at_obj = datetime.utcfromtimestamp(_message['failed_at'])

                    # Format it into a readable format
                    failed_at_readable = failed_at_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    failed_at_readable = ""
                    


                message_list.append(
                    {
                        "id": str(_message['_id']),
                        "number" : _message['number'],
                        "message" : _message['message'],
                        "message_id" : _message['id'],
                        "message_status" : _message['message_status'],
                        "created_at" : human_readable,
                        "template_name" : _message['template_name'],
                        "updated_at": updated_at_human_readable,
                        "sent_at": sent_dt_readable,
                        "delivered_at": delivered_at_readable,
                        "failed_at": failed_at_readable,
                        "code": _message['code'] if "code" in _message else 0,
                        "error_data": _message['error_data'] if "error_data" in _message else "",
                        "title": _message['title'] if "title" in _message else "",
                        "error_message": _message['error_message'] if "error_message" in _message else ""
                    }
                )

            if len(message_list) > 0:
                response_data = {
                    "data": message_list,
                    "count": total_message_count
                }
                return JsonResponse(response_data, status=status.HTTP_200_OK)
            else:
                response_data = {
                    "data": [],
                    "count": 0
                }
                return JsonResponse(response_data, status=status.HTTP_404_NOT_FOUND)

        except Exception as ex:
            print(f"Error: {ex}")
            return JsonResponse({"message": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
