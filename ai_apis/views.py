# Create your views here.
import datetime

from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
import sys
import requests
import json
from UnderdogCrew.settings import API_KEY, OPEN_AI_KEY, GLAM_API_KEY
import pandas as pd
import openai
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from utils.database import MongoDB
import pytz
from ai_apis.schedule_task import schedule_message
import threading
from utils.whatsapp_message_data import send_message_data
from utils.auth import token_required, decode_token
from bson import ObjectId
from utils.auth import current_dollar_price
from utils.send_message_data import TokenBucketLimiter
import logging
from utils.s3_helper import S3Helper
from io import BytesIO


price_per_million_tokens = 0.15  # Price for 1M tokens
tokens_per_million = 1_000_000  # 1M tokens

whatsapp_status = {
    "0": "sent",
    "1": "delivered",
    "2": "read",
    "3": "received",
}

'''
    API for login the user in portal
    request: phone number to send the otp on number
'''
API_TOKEN = API_KEY
GLAM_API_KEY = GLAM_API_KEY


def utc_today_range():
    start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
    return start, end

def count_sent_today(db, user_id):
    start, end = utc_today_range()
    return db.find_documents_count(
        collection_name="whatsapp_message_logs",
        query={
            "user_id": ObjectId(user_id),
            "created_at": {"$gte": start, "$lte": end},
            "message_status": {"$in": ["sent", "delivered", "read", "ok"]}
        }
    )

DAILY_LIMIT = 1000  # your current tier cap



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
            if "example" in component:
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


def send_whatsapp_message(numbers, template_name,text, image_url, user_id, msg_metadata, latitude, longitude, location_name, address, params_fallback_value):
    limiter = TokenBucketLimiter(rate_per_sec=60)  # safe headroom under ~80 MPS default
    for number in numbers:
        limiter.acquire()
        send_message_data(
            number=number,
            template_name=template_name,
            text=text,
            image_url=image_url,
            user_id=user_id,
            metadata=msg_metadata,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            address=address,
            params_fallback_value=params_fallback_value
        )
    return True

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
                'latitude': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Latitude coordinate for location'
                ),
                'longitude': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Longitude coordinate for location'
                ),
                'location_name': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Name or description of the location'
                ),
                'address': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Address or detailed location information'
                ),
                'numbers': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description='Array of phone numbers for single messages (optional, required if message_type=2)'
                ),
                'metadata': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Additional metadata for the message',
                    additional_properties=openapi.Schema(type=openapi.TYPE_STRING)  # Dynamic fields
                ),
                'paramsFallbackValue': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Fallback values for template parameters (e.g., {"Name": "Neel"})',
                    additional_properties=openapi.Schema(type=openapi.TYPE_STRING)
                ),
                "is_select_all": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    default=False,
                    description='While need to send the message to all customer value should be True'
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
    @token_required  # Ensure the user is authenticated
    def post(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            db = MongoDB()
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
        
            request_data = request.data
            template_name = request_data.get("template_name", None)
            msg_metadata = request_data.get("metadata", None)
            latitude = request_data.get("latitude", None)
            longitude = request_data.get("longitude", None)
            location_name = request_data.get("location_name", None)
            address = request_data.get("address", None)
            if template_name == "hotel":
                template_name = "hello_world"

            # Validate required fields
            if not request_data:
                return JsonResponse({"message": "Request body is missing"}, safe=False, status=422)
            if "text" not in request_data:
                return JsonResponse({"message": "Text is missing"}, safe=False, status=422)
            if "message_type" not in request_data:
                return JsonResponse({"message": "Message type is missing"}, safe=False, status=422)
            if template_name is None:
                return JsonResponse({"message": "Template name is missing"}, safe=False, status=422)
            
            user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})
            if user_info is not None:
                waba_id = user_info['waba_id']
                api_key = user_info['api_key']
            else:
                return JsonResponse({"message": "User not found"}, safe=False, status=422)
            
            # --- DAILY CAP ENFORCEMENT ---
            already_sent = count_sent_today(db, user_id)
            remaining = max(0, DAILY_LIMIT - already_sent)

            if remaining <= 0:
                return JsonResponse({
                    "message": "Daily limit reached",
                    "already_sent_today": already_sent,
                    "allowed_today": DAILY_LIMIT,
                    "will_send_now": 0,
                    "skipped_due_to_cap": len(request_data.get('numbers', []))
                }, status=422)
            
            # check if remaining messages is less than numbers count
            if remaining < len(request_data.get('numbers', [])):
                return JsonResponse({
                    "message": "Daily limit reached",
                    "already_sent_today": already_sent,
                    "allowed_today": DAILY_LIMIT,
                    "will_send_now": remaining,
                    "skipped_due_to_cap": len(request_data.get('numbers', []))
                }, status=422)
            
            # limit to remaining quota
            numbers_to_send = request_data.get('numbers', [])[:remaining]
            skipped = max(0, len(request_data.get('numbers', [])) - len(numbers_to_send))
            
            
            template_url = f"https://graph.facebook.com/v21.0/{waba_id}/message_templates?name={template_name}"
            API_KEY = api_key

            headers = {
                'Authorization': f'Bearer {API_KEY}'
            }
            template_response = requests.request("GET", template_url, headers=headers)
            if template_response.status_code != 200:
                return JsonResponse({"message": "Template is missing"}, safe=False, status=422)

            text = request_data['text']
            schedule_type = request_data['schedule_type'] if "schedule_type" in request_data else 1
            file_path = request_data['fileUrl'] if "fileUrl" in request_data else ""
            message_type = request_data['message_type']

            image_url = request_data.get('image_url', "")
            numbers = request_data.get('numbers', [])
            is_select_all = request_data.get('is_select_all', False)
            params_fallback_value = request_data.get("paramsFallbackValue", {})

            if is_select_all is True:
                pipeline = [
                    { "$match": { "user_id":user_id } },
                    { "$group": { "_id": "$number", "customer": { "$first": "$$ROOT" } } },
                    { "$replaceRoot": { "newRoot": "$customer" } }
                ]
                results = db.aggregate(collection_name="customers", pipeline=pipeline)
                for customer in results:
                    numbers.append(customer['number'])

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

            if schedule_type == 2 and file_path == "":
                return JsonResponse(
                    {"message": "file is required for message_type 1"},
                    safe=False,
                    status=422
                )

            if template_name == "insurance_policy" and str(user_id) == "67c1cf4c2763ce36e17d145e":
                # Create a thread for the schedule_message function
                message_thread = threading.Thread(target=schedule_message, args=(file_path, user_id, image_url, template_name, text))
                message_thread.start()  # Start the thread
                return JsonResponse(
                    {"message": "Message scheduled successfully"},
                    safe=False,
                    status=200
                )
            
            threading.Thread(target=send_whatsapp_message, args=(numbers,
                                                             template_name,
                                                             text,
                                                             image_url,
                                                             user_id,
                                                             msg_metadata,
                                                             latitude,
                                                             longitude,
                                                             location_name,
                                                             address,
                                                             params_fallback_value,)
                                                             ).start()

            return JsonResponse({"message": "Messages sent successfully", 
            "skipped": skipped, 
            "will_send_now": remaining,
            "allowed_today": DAILY_LIMIT,
            "already_sent_today": already_sent,
            "numbers_to_send": numbers_to_send}, safe=False, status=200)

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
            guid = entry[0]['id']
            value = changes[0]['value']
            phone_number_id = value['metadata']['phone_number_id']
            statuses = value['statuses'] if "statuses" in value else []
            hub_challenge = "EAANWlQY0U2gBOxjQ1WIYomX99g9ZBarEiZBAftiZBYGVgvGWJ8OwZBwUdCEmgA1TZBZB9XT"
            user_info = db.find_document("users", query={"phone_number_id": phone_number_id})
            if user_info is None:
                user_info = db.find_document("users", query={"business_id": phone_number_id})
            
            auto_reply_enabled = user_info['auto_reply_enabled'] if "auto_reply_enabled" in user_info else False
            reply_webhook_url = user_info.get('reply_webhook_url', "")
            status_webhook_url = user_info.get('status_webhook_url', "")

            if len(statuses) == 0:
                try:
                    if user_info:
                        print("user_info found")
                        phone_number_id = phone_number_id #user_info['phone_number_id'] if "phone_number_id" in user_info else ""

                        reply_payload = {
                            "created_at": datetime.datetime.now()
                        }

                        display_phone_number =value['metadata']['display_phone_number']
                        if "text" in value['messages'][0]:
                            messages = value['messages'][0]['text']['body']
                        elif "button" in value['messages'][0]:
                            messages = value['messages'][0]['button']['payload']
                        else:
                            messages = ""
                        
                        from_number = value['messages'][0]['from']
                        messages_type = value['messages'][0]['type']
                        reply_payload['To'] = phone_number_id
                        reply_payload['From'] = from_number
                        reply_payload['content_type'] = messages_type
                        reply_payload['guid'] = value['messages'][0]['id']

                        if str(user_info['_id']) == "67c1cf4c2763ce36e17d145e":
                            last_send_message = db.find_documents(
                                collection_name="whatsapp_message_logs",
                                query={
                                    "number": from_number,
                                    "status": {"$ne": "received"},
                                    "template_name" : {"$in": ["insurance_policy", "insurance_policy_with_image"]}
                                },
                                sort=[('_id', -1)],limit=1
                            )
                            if not last_send_message:
                                pass
                            else:
                                phone_number = 9898621300
                                if "metadata" in last_send_message[0]:
                                    metadata = last_send_message[0]['metadata']
                                    if "policy" in metadata:
                                        pass
                                    else:
                                        metadata = {
                                            "name": from_number,
                                            "company_name": "-",
                                            "policy": "-",
                                            "date": "-"
                                        }
                                    metadata['user_reply'] = messages
                                    send_message_data(
                                        number=phone_number, # do not remove this number as we need to send the replied to Urvish number
                                        template_name="insurance_reply",
                                        text="",
                                        image_url="",
                                        user_id=str(user_info['_id']),
                                        metadata=metadata,
                                        entry=metadata
                                    )
                                else:
                                    metadata = {
                                        "name": from_number,
                                        "company_name": "-",
                                        "policy": "-",
                                        "date": "-"
                                    }
                                    metadata['user_reply'] = messages
                                    send_message_data(
                                        number=phone_number, # do not remove this number as we need to send the replied to Urvish number
                                        template_name="insurance_reply",
                                        text="",
                                        image_url="",
                                        user_id=str(user_info['_id']),
                                        metadata=metadata,
                                        entry=metadata
                                    )
                        logging.info(f"messages_type: {messages_type}")
                        if messages_type == "text" or messages_type == "button":
                            reply_payload['message'] = messages
                            whatsapp_status_logs = {
                                "number": from_number,
                                "message": messages,
                                "user_id": str(user_info['_id']),
                                "price": 0,
                                "id": value['messages'][0]['id'],
                                "message_status": "received",
                                "created_at": datetime.datetime.now(),
                                "updated_at": datetime.datetime.now(),
                                "template_name": "template_name",
                                "code": 0,
                                "title": "",
                                "error_message": "",
                                "attachment": False,
                                "attachment_url": "",
                                "error_data": "",
                                "sent_at" : int(value['messages'][0]['timestamp']),
                                "delivered_at" : int(value['messages'][0]['timestamp']),
                                "read_at" : int(value['messages'][0]['timestamp'])
                            }
                            db.create_document('whatsapp_message_logs', whatsapp_status_logs)
                            logging.info("Replied Saved in database")
                        
                        if messages_type == "interactive":
                            interactive = value['messages'][0]['interactive']['nfm_reply'] if "nfm_reply" in value['messages'][0]['interactive'] else None
                            if interactive:
                                reply_payload['message'] = interactive
                                whatsapp_status_logs = {
                                    "number": from_number,
                                    "message": interactive['response_json'],
                                    "user_id": str(user_info['_id']),
                                    "price": 0,
                                    "id": value['messages'][0]['id'],
                                    "message_status": "received",
                                    "created_at": datetime.datetime.now(),
                                    "updated_at": datetime.datetime.now(),
                                    "template_name": "interactive",
                                    "code": 0,
                                    "title": "",
                                    "error_message": "",
                                    "attachment": False,
                                    "attachment_url": "",
                                    "error_data": "",
                                    "sent_at" : int(value['messages'][0]['timestamp']),
                                    "delivered_at" : int(value['messages'][0]['timestamp']),
                                    "read_at" : int(value['messages'][0]['timestamp'])
                                }
                                db.create_document('whatsapp_message_logs', whatsapp_status_logs)
                        
                        if messages_type in ["video", "image", "audio", "document"]:
                            attachment_url = ""
                            attachment = value['messages'][0][messages_type]['id']
                            caption = value['messages'][0][messages_type]['caption'] if "caption" in value['messages'][0][messages_type] else ""

                            url = f"https://graph.facebook.com/v19.0/{attachment}?phone_number_id={phone_number_id}"

                            payload = {}
                            headers = {
                                'Authorization': f'Bearer {API_TOKEN}',
                            }

                            response = requests.request("GET", url, headers=headers, data=payload)

                            if response.status_code == 200:
                                attachment_id = response.json()['url']
                                mime_type = response.json()['mime_type']
                                extension = mime_type.split("/")[-1]
                                # payload = {}
                                headers = {
                                  'Authorization': f'Bearer {API_TOKEN}'
                                }

                                attachment_response = requests.request("GET", attachment_id, headers=headers, data=payload)
                                if attachment_response.status_code == 200:
                                    content = attachment_response.content
                                    # Create a file-like object from the content
                                    video_file = BytesIO(content)
                                    video_file.name = f"{attachment}.{extension}"
                                    
                                    # Upload to S3
                                    s3_helper = S3Helper()
                                    attachment_url = s3_helper.upload_media_file(
                                        file_obj=video_file,
                                        folder_name=f"{user_info['_id']}/whatsapp_media",  # or whatever folder you prefer
                                        file_extension=extension,
                                        content_type=mime_type,
                                        file_name=f"{attachment}.{extension}"
                                    )
                                else:
                                    attachment_url = ""
                            if attachment_url is not None and attachment_url != "":
                                reply_payload['media_url'] = attachment_url
                                reply_payload['content_type'] = messages_type
                                reply_payload['guid'] = value['messages'][0]['id']
                                whatsapp_status_logs = {
                                    "number": from_number,
                                    "message": caption,
                                    "user_id": str(user_info['_id']),
                                    "price": 0,
                                    "id": value['messages'][0]['id'],
                                    "message_status": "received",
                                    "created_at": datetime.datetime.now(),
                                    "updated_at": datetime.datetime.now(),
                                    "template_name": messages_type,
                                    "code": 0,
                                    "title": "",
                                    "error_message": "",
                                    "attachment": True,
                                    "attachment_url": attachment_url,
                                    "error_data": "",
                                    "sent_at" : int(value['messages'][0]['timestamp']),
                                    "delivered_at" : int(value['messages'][0]['timestamp']),
                                    "read_at" : int(value['messages'][0]['timestamp'])
                                }
                                db.create_document('whatsapp_message_logs', whatsapp_status_logs)
                        
                        if reply_webhook_url is not None and reply_webhook_url != "":
                            reply_webhook_response = reply_payload
                            reply_webhook_response = requests.post(reply_webhook_url, json=reply_webhook_response)
                            logging.info(f"Reply webhook response: {reply_webhook_response.json()}")
                            if reply_webhook_response.status_code == 200:
                                logging.info(f"Reply webhook sent successfully")
                            else:
                                logging.error(f"Failed to send reply webhook")
                        
                        if auto_reply_enabled is True:
                            openai_data = {
                                "model": "gpt-4o-mini",
                                "messages": [
                                    {"role": "system", "content": "You are a helpful assistant."},
                                    {"role": "user", "content": messages}
                                ]
                            }

                            openai_api_key = OPEN_AI_KEY
                            openai_headers = {
                                "Authorization": f"Bearer {openai_api_key}",
                                "Content-Type": "application/json",
                            }

                            openai_response = requests.post("https://api.openai.com/v1/chat/completions", json=openai_data, headers=openai_headers)
                            logging.info(f"Open AI response: {openai_response.json()}")
                            uses = openai_response.json()['usage']
                            total_tokens = uses['total_tokens']
                            prompt_tokens = uses['prompt_tokens']
                            completion_tokens = uses['completion_tokens']
                            response_text = openai_response.json()['choices'][0]['message']['content']
                            payload = json.dumps(
                                {
                                    "messaging_product": "whatsapp",
                                    "recipient_type": "individual",
                                    "to": from_number,
                                    "type": "text",
                                    "text": {
                                        "preview_url": False,
                                        "body": response_text
                                    }
                                }
                            )
                            logging.info("from_number", from_number)
                            headers = {
                                'Authorization': 'Bearer ' + API_TOKEN,
                                'Content-Type': 'application/json',
                                'Cookie': 'ps_l=0; ps_n=0'
                            }
                            url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
                            response = requests.request("POST", url, headers=headers, data=payload)
                            logging.info(f"message: {response.json()}")
                            if response.status_code == 200:
                                # Calculate the price and ensure it's stored as a float
                                price = float((total_tokens / tokens_per_million) * price_per_million_tokens)
                                # Print the result
                                logging.info(f"Price for {total_tokens} tokens: ${price}")
                                whatsapp_status_logs = {
                                    "number": from_number,
                                    "message": response_text,
                                    "user_id": str(user_info['_id']),
                                    "price": price*0.875,
                                    "id": response.json()['messages'][0]["id"],
                                    "message_status": response.json()['messages'][0]["message_status"] if "message_status" in response.json()['messages'][0] else "sent",
                                    "created_at": datetime.datetime.now(),
                                    "updated_at": datetime.datetime.now(),
                                    "template_name": "template_name",
                                    "code": 0,
                                    "title": "",
                                    "error_message": "",
                                    "error_data": "",
                                }
                                db.create_document('whatsapp_message_logs', whatsapp_status_logs)

                except Exception as error:
                    logging.error(f"Error coming: {str(error)}")
                
                return HttpResponse(hub_challenge)

            # need to add the logs in database
            user = db.find_document('whatsapp_message_logs', {'id': statuses[0]['id']})
            if user:
                code = 0
                title = ""
                message = ""
                error_data = ""
                recipient_id = ""
                try:
                    errors = statuses[0]['errors'][0]
                    recipient_id = statuses[0]['recipient_id']
                    status_id = statuses[0]['id']
                    code = errors['code']
                    title = errors['title']
                    message = errors['message']
                    error_data = errors['error_data']['details']
                except:
                    pass

                if status_webhook_url is not None and status_webhook_url != "":
                    ## we need to send the status webhook to the url
                    status_webhook_response = f"?To={recipient_id}&From={user['number']}&REASON_CODE=200&GUID={status_id}&MSG_STATUS={statuses[0]['status']}&DELIVERED_DATE={statuses[0]['timestamp']}&SUBMIT_DATE={statuses[0]['timestamp']}"
                    status_webhook_response = requests.get(status_webhook_url + status_webhook_response)
                    logging.info(f"Status webhook response: {status_webhook_response.json()}")

                db.update_document(
                    'whatsapp_message_logs',
                    {'_id': user['_id']},
                    {
                        'message_status': statuses[0]['status'], 
                        f"{statuses[0]['status']}_at": int(statuses[0]['timestamp']),
                        "updated_at": datetime.datetime.now(),
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
            
            logging.info(f"msg_type: {msg_type}")
            logging.info(f"messages: {messages}")
            
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
                logging.info("from_number", from_number)
                headers = {
                    'Authorization': 'Bearer ' + API_TOKEN,
                    'Content-Type': 'application/json',
                    'Cookie': 'ps_l=0; ps_n=0'
                }
                url = "https://graph.facebook.com/v19.0/450885871446042/messages"
                response = requests.request("POST", url, headers=headers, data=payload)
                logging.info(response.json())

            response_data = {
                "message": "Message send successfully",
            }
            return HttpResponse(hub_challenge)
        except Exception as ex:
            logging.error("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
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
            logging.info(f"challenge {challenge}")
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
    @token_required  # Ensure the user is authenticated
    def post(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
                print(f"user id: {user_id}")
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
        
            db = MongoDB()
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
                    "price": 0.08,
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
    @token_required  # Ensure the user is authenticated
    def post(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        token = request.headers.get('Authorization')  # Extract the token from the Authorization header
        if token is None or not token.startswith('Bearer '):
            return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

        token = token.split(' ')[1]  # Get the actual token part
        user_info = decode_token(token)  # Decode the token to get user information
        
        # Check if user_info is a dictionary
        if isinstance(user_info, dict) and 'user_id' in user_info:
            user_id = user_info['user_id']  # Access user_id from the decoded token
            print(f"user id: {user_id}")
        else:
            return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)

        try:
            db = MongoDB()
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
                uses = response.json()['usage']
                total_tokens = uses['total_tokens']
                prompt_tokens = uses['prompt_tokens']
                completion_tokens = uses['completion_tokens']
                response_text = response.json()['choices'][0]['message']['content']


                if "Hindi:" in response_text and text_type == 5:
                    response_text = response_text.split("Hindi:")[1]

                # Calculate the price and ensure it's stored as a float
                price = float((total_tokens / tokens_per_million) * price_per_million_tokens)
                # Print the result
                print(f"Price for {total_tokens} tokens: ${price}")

                text_generation_logs = {
                    "message": text,
                    "user_id": user_id,
                    "created_at": int(datetime.datetime.now().timestamp()),
                    "response": response_text,
                    "input_token": prompt_tokens,
                    "price": price,
                    "output_token": completion_tokens,
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
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
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
    @token_required  # Ensure the user is authenticated
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
                print(f"user id: {user_id}")
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            # Parse optional query parameters
            start_date = request.query_params.get("start_date", None)
            end_date = request.query_params.get("end_date", None)

            # Validate and process date formats
            if start_date:
                try:
                    start_date_gmt = datetime.datetime.strptime(start_date, "%Y-%m-%d")

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    start_date_localized = kolkata_timezone.localize(start_date_gmt)
                    # Convert to timestamp
                    start_date = int(start_date_localized.timestamp())
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
                    end_date_localized = kolkata_timezone.localize(end_date_gmt)
                    # Convert to timestamp
                    end_date = int(end_date_localized.timestamp())
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid end_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )


            # Connect to the database
            db = MongoDB()

            # Build query filter based on dates
            filters = {}
            user_query = {}
            if user_id == "superadmin":
                query_filter = {}
                text_filter = {}
            else:    
                query_filter = {"user_id": user_id}
                text_filter = {"user_id": user_id}
            if start_date:
                query_filter["created_at"] = {"$gte": start_date}
                text_filter["created_at"] = {"$gte": start_date}
                filters["created_at"] = {"$gte": start_date}
                user_query['created_at'] = {"$gte": start_date}
            if end_date:
                if "created_at" in query_filter:
                    query_filter["created_at"]["$lte"] = end_date
                    text_filter["created_at"]["$lte"] = end_date
                    filters["created_at"]["$lte"] = end_date
                    user_query['created_at']["$lte"] = end_date
                else:
                    query_filter["created_at"] = {"$lte": end_date}
                    text_filter["created_at"] = {"$lte": end_date}
                    filters["created_at"] = {"$lte": end_date}
                    user_query['created_at'] = {"$lte": end_date}

            
            ## we need to add the chart data
            chart_query = {
                "user_id": user_id,
                # "sent_at": { "$gt": 0 } # Optional safeguard for sent_at
                "message_status" : {"$nin": ["failed", "error"]}
            }
            if start_date and end_date:
                chart_query['created_at'] = {
                    "$gte": start_date,
                    "$lte": end_date
                }

            print(f"chart query: {chart_query}")

            pipeline = [
                {
                    "$match": chart_query
                },
                {
                    "$addFields": {
                    "sent_date": {
                        "$dateToString": {
                        "format": "%d/%m/%Y",
                        "date": { "$toDate": { "$multiply": ["$sent_at", 1000] } }
                        }
                    }
                    }
                },
                {
                    "$group": {
                    "_id": "$sent_date",
                    "sent": { "$sum": 1 },
                    "delivered": {
                        "$sum": {
                        "$cond": [{ "$gt": ["$delivered_at", 0] }, 1, 0]
                        }
                    },
                    "read": {
                        "$sum": {
                        "$cond": [{ "$gt": ["$read_at", 0] }, 1, 0]
                        }
                    }
                    }
                },
                {
                    "$project": {
                    "_id": 0,
                    "date": "$_id",
                    "sent": 1,
                    "delivered": 1,
                    "read": 1
                    }
                },
                {
                    "$sort": {
                    "date": 1
                    }
                }
            ]

            print(f"pipeline: {pipeline}")

            mongo_result = db.aggregate(collection_name="whatsapp_message_logs", pipeline=pipeline)
            # Convert the result to a dictionary for quick lookup
            result_map = {item['date']: item for item in mongo_result}
            # Generate all dates between start and end
            if start_date and end_date:
                current_date = start_date
                final_result = []

                while current_date <= end_date:
                    formatted_date = current_date
                    if formatted_date in result_map:
                        final_result.append(result_map[formatted_date])
                    else:
                        final_result.append({
                            "date": formatted_date,
                            "read": 0,
                            "delivered": 0,
                            "sent": 0
                        })
                    current_date += 86400  # Add one day in seconds
            else:
                final_result = mongo_result
            
            dollar_price = current_dollar_price()
            # Build filter conditions
            # Get total billing from WhatsApp logs
            whatsapp_logs = db.find_documents('whatsapp_message_logs', filters)
            whatsapp_total = sum(log.get('price', 0) for log in whatsapp_logs)

            # Get total billing from Image Generation logs
            image_logs = db.find_documents('image_generation_logs', filters)
            image_total = sum(log.get('price', 0) for log in image_logs)
            image_total = dollar_price * image_total

            # Get total billing from Text Generation logs
            text_logs = db.find_documents('text_generation_logs', filters)
            text_total = sum(log.get('price', 0) for log in text_logs)
            text_total = dollar_price * text_total

            # Calculate final total
            total_price = whatsapp_total + image_total + text_total
            
            # Calculate CGST and SGST
            cgst = total_price * 0.09  # 9% of total_price
            sgst = total_price * 0.09  # 9% of total_price
            
            # Add CGST and SGST to total_price
            total_price_with_tax = total_price + cgst + sgst

            print(f"query_filter: {query_filter}")
            # Fetch data from database
            total_message = len(db.find_documents("whatsapp_message_logs", query_filter))
            query_filter['status'] = "delivered"
            total_message_received = len(db.find_documents("whatsapp_message_logs", query_filter))
            text_generation_logs = len(db.find_documents("text_generation_logs", text_filter))
            image_generation_logs = len(db.find_documents("image_generation_logs", text_filter))
            active_user_count = len(db.find_documents("users", user_query))

            response_data = {
                "total_message": total_message,
                "total_message_received": total_message_received,
                "text_generation_logs": text_generation_logs,
                "image_generation_logs": image_generation_logs,
                "whatsapp_total": f"₹{round(whatsapp_total, 2)}",
                "image_total": f"₹{round(image_total, 2)}",
                "text_total": f"₹{round(text_total, 2)}",
                "total_price": f"₹{round(total_price, 2)}",
                "active_user_count": active_user_count,
                "final_price": f"₹{round(total_price_with_tax, 2)}",
                "cgst": f"₹{round(cgst, 2)}",
                "sgst": f"₹{round(sgst, 2)}",
                "charts": {
                    "linechart": final_result
                }
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
    @token_required  # Ensure the user is authenticated
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
                print(f"user id: {user_id}")
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            # Parse optional query parameters
            start_date = request.query_params.get("start_date", None)
            end_date = request.query_params.get("end_date", None)
            whatsapp_status_text = request.query_params.get("status", None)
            skip = int(request.query_params.get("skip", 0))
            limit = int(request.query_params.get("limit", 20))

            # Validate and process date formats
            if start_date:
                try:
                    start_date_gmt = datetime.datetime.strptime(start_date, "%Y-%m-%d")

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    start_date_localized = kolkata_timezone.localize(start_date_gmt)
                    # Convert to timestamp
                    start_date = int(start_date_localized.timestamp())
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
                    end_date_localized = kolkata_timezone.localize(end_date_gmt)
                    # Convert to timestamp
                    end_date = int(end_date_localized.timestamp())
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
            if whatsapp_status_text:
                if whatsapp_status_text in whatsapp_status:
                    query_filter['message_status'] = whatsapp_status[whatsapp_status_text]
                    text_filter['message_status'] = whatsapp_status[whatsapp_status_text]
            
            print(f"text filter: {text_filter}")
            # Fetch data from database
            sort_order = [("_id", -1)]  # Sorting in descending order
            skip_count = skip
            limit_count = limit
            total_message = db.find_documents("whatsapp_message_logs", query_filter, sort=sort_order, skip=skip_count, limit=limit_count)
            total_message_count = len(db.find_documents("whatsapp_message_logs", query_filter))

            message_list = []
            for _message in total_message:
                # Convert ISO string to datetime object
                try:
                    human_readable = datetime.datetime.strftime(_message['created_at'], "%Y-%m-%d %H:%M:%S")
                except:
                    try:
                        human_readable = datetime.datetime.fromtimestamp(_message['created_at']).strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        human_readable = ""

                # Convert to a human-readable format
                # human_readable = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                
                try:
                    updated_at_human_readable = datetime.datetime.strftime(_message['updated_at'], "%Y-%m-%d %H:%M:%S")
                    # Convert to a human-readable format
                    # updated_at_human_readable = updated_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    updated_at_human_readable = ""

                try:
                    # Convert to a datetime object
                    sent_dt_obj = datetime.datetime.utcfromtimestamp(_message['sent_at'])

                    # Format it into a readable format
                    sent_dt_readable = sent_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    sent_dt_readable = ""
                
                try:
                    # Convert to a datetime object
                    read_at_obj = datetime.datetime.utcfromtimestamp(_message['read_at'])

                    # Format it into a readable format
                    read_at_readable = read_at_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    read_at_readable = ""
                

                try:
                    # Convert to a datetime object
                    delivered_at_obj = datetime.datetime.utcfromtimestamp(_message['delivered_at'])

                    # Format it into a readable format
                    delivered_at_readable = delivered_at_obj.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    delivered_at_readable = ""


                try:
                    # Convert to a datetime object
                    failed_at_obj = datetime.datetime.utcfromtimestamp(_message['failed_at'])

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
                        "read_at": read_at_readable,
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



class WhatsAppMessage(APIView):
    @swagger_auto_schema(
        operation_description="Send a message via WhatsApp",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'text': openapi.Schema(type=openapi.TYPE_STRING, description='Text message to send'),
                "number": openapi.Schema(type=openapi.TYPE_STRING, description='number on which we need to send the message'),
                'url': openapi.Schema(type=openapi.TYPE_STRING, description='URL of the image or file'),

            },
            required=['text', 'number']
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
    @token_required  # Ensure the user is authenticated
    def post(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            db = MongoDB()
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
                print(f"user id: {user_id}")
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            
            request_data = request.data
            # Validate required fields
            if not request_data:
                return JsonResponse({"message": "Request body is missing"}, safe=False, status=422)
            if "text" not in request_data:
                return JsonResponse({"message": "Text is missing"}, safe=False, status=422)

            headers = {
                'Authorization': 'Bearer ' + API_TOKEN,
                'Content-Type': 'application/json'
            }

            text = request_data['text']
            image_url = request_data.get('url', "")
            number = request_data.get('number', "")

            if number == "":
                return JsonResponse(
                    {"message": "Numbers is required"},
                    safe=False,
                    status=422
                )
            
            user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})

            if user_info is not None:
                business_id = user_info['phone_number_id']
            else:
                business_id = "450885871446042"

            url = f"https://graph.facebook.com/v19.0/{business_id}/messages"
            payload = json.dumps({
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": f"91{number}",
                "type": "text",
                "text": {
                    "body": text
                }
            })
            print(payload)
            print(f"url: {url}")
            response = requests.request("POST", url, headers=headers, data=payload)
            print(response.json())
            if response.status_code == 200:
                whatsapp_status_logs = {
                    "number": f"91{number}",
                    "message": text,
                    "user_id": user_id,
                    "price": 0.125,
                    "id": response.json()['messages'][0]["id"],
                    "message_status": "sent",
                    "created_at": datetime.datetime.now(),
                    "updated_at": datetime.datetime.now(),
                    "template_name": "manual"
                }
                db.create_document('whatsapp_message_logs', whatsapp_status_logs)
            else:
                whatsapp_status_logs = {
                    "number": f"91{number}",
                    "message": text,
                    "user_id": user_id,
                    "price": 0,
                    "id": "",
                    "message_status": "error",
                    "created_at": datetime.datetime.now(),
                    "updated_at": datetime.datetime.now(),
                    "template_name": "manual",
                    "code": response.json()['error']['code'],
                    "title": response.json()['error']['type'],
                    "error_message": response.json()['error']['message'],
                    "error_data": response.json()['error']['message'],
                }
                db.create_document('whatsapp_message_logs', whatsapp_status_logs)

            return JsonResponse({"message": "Messages sent successfully"}, safe=False, status=200)

        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            return JsonResponse({"message": "Something went wrong"}, safe=False, status=500)

          
class UserDashboardData(APIView):
    @swagger_auto_schema(
        operation_description="Fetch user dashboard data",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
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
    @token_required  # Ensure the user is authenticated
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information

            sent_count = 0
            delivered_count = 0
            read_count = 0
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            
            ## we need to get the user info from the database
            db = MongoDB()
            user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})
            if user_info is None:
                return JsonResponse({"message": "User not found"}, status=404)
            
            ## we need to get the phone number id from the database
            waba_id = user_info['waba_id']
            meta_business_number = user_info['meta_business_number']
            meta_business_number = meta_business_number.replace("+", "")
            meta_business_number = meta_business_number.replace(" ", "")
            api_key = user_info['api_key']
                        
            # Parse optional query parameters
            start_date = request.query_params.get("start_date", None)
            end_date = request.query_params.get("end_date", None)

            if start_date is None and end_date is None:
                return JsonResponse({"message": "Start date and end date are required"}, status=400)

            # Validate and process date formats
            if start_date:
                try:
                    start_date_gmt = datetime.datetime.strptime(start_date, "%Y-%m-%d")

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    start_date_localized = kolkata_timezone.localize(start_date_gmt)
                    # Convert to timestamp
                    start_date = int(start_date_localized.timestamp())
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
                    end_date_localized = kolkata_timezone.localize(end_date_gmt)
                    # Convert to timestamp
                    end_date = int(end_date_localized.timestamp())
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid end_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            api_url = f"https://graph.facebook.com/v23.0/{waba_id}?fields=analytics.start({start_date}).end({end_date}).granularity(DAY).phone_numbers([{meta_business_number}])"
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                if "analytics" in response.json():
                    if "data_points" in response.json()['analytics']:
                        analytics_data = response.json()['analytics']['data_points']
                        for data in analytics_data:
                            sent_count += data['sent'] if 'sent' in data else 0
                            delivered_count += data['delivered'] if 'delivered' in data else 0
                            read_count += data['read'] if 'read' in data else 0
                        return JsonResponse(
                            {
                                "sent_count": sent_count,
                                "delivered_count": delivered_count,
                                "read_count": read_count,
                                "message": "Analytics data fetched successfully",
                                "data": analytics_data
                            }, status=status.HTTP_200_OK)
                    else:
                        return JsonResponse({"message": "No analytics data found"}, status=404)
                else:
                    return JsonResponse({"message": "No analytics data found"}, status=404)
            else:
                return JsonResponse({"message": response.text}, status=response.status_code)

        except Exception as ex:
            print(f"Error: {ex}")
            return JsonResponse({"message": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
class CustomerCredits(APIView):
    @swagger_auto_schema(
        operation_description="Fetch customer credits",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                "template_type",
                openapi.IN_QUERY,
                description="Template type(1 for marketing, 2 for utility, 3 for authentication)",
                type=openapi.TYPE_INTEGER,
                required=True
            ),
            openapi.Parameter(
                "customer_count",
                openapi.IN_QUERY,
                description="Number of customers",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                "is_select_all",
                openapi.IN_QUERY,
                description="Need to send messages to all customers",
                type=openapi.TYPE_BOOLEAN,
                required=True,
                default=False
            )
        ],
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
    @token_required  # Ensure the user is authenticated
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        '''
            API For calculating the credits required for the template
                - Get the user info from the database
                - Get the template type from the request
                - Get the customer count from the request
                - Calculate the credits required for the template
                - Check if the user has sufficient credits
                - Return the response
            template_type:
                1: marketing
                2: utility
                3: authentication
            customer_count:
                number of customers
            credits:
                credits required for the template
            remaining_credits:
                remaining credits after the transaction
            user_credits:
                total credits of the user
        '''
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            
            # Check if user_info is a dictionary
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            
            ## we need to get the user info from the database
            db = MongoDB()
            is_select_all = request.query_params.get("is_select_all", False)
            user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})
            if user_info is None:
                return JsonResponse({"message": "User not found"}, status=404)
            
            template_type = int(request.query_params.get("template_type", 0))
            if template_type == 0:
                return JsonResponse({"message": "Template type is required"}, status=400)
            
            if template_type not in [1, 2, 3]:
                return JsonResponse({"message": "Invalid template type"}, status=400)
            
            customer_count = int(request.query_params.get("customer_count", 0))
            print(f"customer_count: {customer_count}")
            print(f"is_select_all: {is_select_all}")
            if customer_count is None and is_select_all is False:
                return JsonResponse({"message": "Customer count is required"}, status=400)
            elif is_select_all is True:
                pipeline = [{
                    "$match": {
                        "user_id" : user_id
                    }
                },
                {
                    "$group": {
                    "_id": "$number"
                    }
                },
                {
                    "$count": "uniqueCustomerCount"
                }
                ]
                customer_agg_count = db.aggregate_count(collection_name="customers", pipeline=pipeline)
                print(f"customer_agg_count: {customer_agg_count}")
                if customer_agg_count:
                    customer_count = customer_agg_count[0]['uniqueCustomerCount']
                    print("Unique customers:", customer_count)
            
            if customer_count is None:
                return JsonResponse({"message": "Customer count is required"}, status=400)

            ## we need to get the credits from the database
            user_credits = user_info['default_credit']
            
            if template_type == 1:
                credits = round(customer_count * 0.875, 2)
            elif template_type == 2:
                credits = round(customer_count * 0.125, 2)
            elif template_type == 3:
                credits = round(customer_count * 0.125, 2)
            else:
                return JsonResponse({"message": "Invalid template type"}, status=400)
            
            if user_credits < credits:
                return JsonResponse({"message": "Insufficient credits", "credits_required": credits, "user_credits": user_credits}, status=400)
            
            response = {
                "message": "Credits fetched successfully",
                "credits_required": credits,
                "remaining_credits": round(user_credits - credits, 2),
                "user_credits": user_credits
            }
            
            return JsonResponse(response, status=200)
            
        except Exception as ex:
            print(f"Error: {ex}")
            return JsonResponse({"message": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UserWebhookDetails(APIView):
    @swagger_auto_schema(
        operation_description="Fetch user webhook details",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
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
    @token_required  # Ensure the user is authenticated
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            
            ## we need to get the user info from the database
            db = MongoDB()
            user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})
            if user_info is None:
                return JsonResponse({"message": "User not found"}, status=404)
            
            ## we need to get the webhook details from the database
            reply_webhook_url = user_info.get('reply_webhook_url', "")
            status_webhook_url = user_info.get('status_webhook_url', "")
            api_key = user_info.get('webhook_api_key', "")
            reply_webhook_response = {
                "created_at": "<datetime>",
                "To":"<phone_number>",
                "From":"<phone_number>",
                "message":"<message>",
                "content_type":"<content_type>",
                "media_url":"<media_url>"
            }
            response = {
                "message": "Webhook details fetched successfully",
                "reply_webhook_url": reply_webhook_url,
                "status_webhook_url": status_webhook_url,
                "webhook_api_key": api_key,
                "reply_webhook_response": reply_webhook_response,
                "status_webhook_response": "?To=%p&From=%P&REASON_CODE=%2&GUID=%5&MSG_STATUS=%16&DELIVERED_DATE=%3&SUBMIT_DATE=%14&DLT_TEMPLATEID=%dlt_templateid&STATUS_ERROR=%4"
            }
            return JsonResponse(response, status=200)
        except Exception as ex:
            print(f"Error: {ex}")
            return JsonResponse({"message": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        operation_description="Update user webhook details",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'reply_webhook_url': openapi.Schema(type=openapi.TYPE_STRING, description="Reply webhook URL"),
                'status_webhook_url': openapi.Schema(type=openapi.TYPE_STRING, description="Status webhook URL"),
            },
            required=['reply_webhook_url', 'status_webhook_url', 'webhook_api_key']
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
    @token_required  # Ensure the user is authenticated
    def post(self, request, current_user_id=None, current_user_email=None):
        try:
            token = request.headers.get('Authorization')  # Extract the token from the Authorization header
            if token is None or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]  # Get the actual token part
            user_info = decode_token(token)  # Decode the token to get user information
            if isinstance(user_info, dict) and 'user_id' in user_info:
                user_id = user_info['user_id']  # Access user_id from the decoded token
            else:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)
            
            ## we need to get the user info from the database
            db = MongoDB()
            user_info = db.find_document(collection_name="users", query={"_id": ObjectId(user_id)})
            if user_info is None:
                return JsonResponse({"message": "User not found"}, status=404)
            
            ## we need to update the webhook details in the database
            reply_webhook_url = request.data.get('reply_webhook_url', "")
            status_webhook_url = request.data.get('status_webhook_url', "")
            result = db.update_document(collection_name="users", query={"_id": ObjectId(user_id)}, update_data={
                "reply_webhook_url": reply_webhook_url,
                "status_webhook_url": status_webhook_url,
            })
            if result.modified_count == 0:
                return JsonResponse({"message": "Failed to update webhook details"}, status=400)
            response = {
                "message": "Webhook details updated successfully",
                "reply_webhook_url": reply_webhook_url,
                "status_webhook_url": status_webhook_url,
            }
            return JsonResponse(response, status=200)
        except Exception as ex:
            print(f"Error: {ex}")
            return JsonResponse({"message": "Internal Server Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)