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


'''
    API for login the user in portal
    request: phone number to send the otp on number
'''
API_TOKEN = API_KEY


class SendMessage(APIView):
    @swagger_auto_schema(
        operation_description="Send a message via WhatsApp",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'text': openapi.Schema(type=openapi.TYPE_STRING, description='Text message to send'),
                'fileUrl': openapi.Schema(type=openapi.TYPE_STRING, description='URL of the Excel file'),
                'image_url': openapi.Schema(type=openapi.TYPE_STRING, description='Image URL (optional)'),
            },
            required=['text', 'fileUrl']
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
            print(f"API_TOKEN: {API_TOKEN}")
            url = "https://graph.facebook.com/v19.0/450885871446042/messages"
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
            elif "fileUrl" not in request_data:
                response_data = {
                    "message": "to is missing",
                }
                return JsonResponse(response_data, safe=False, status=422)
            else:
                text = request_data['text']
                image_url = request_data['image_url'] if "image_url" in request_data else ""
                # Load the Excel file
                file_path = request_data['fileUrl']
                df = pd.read_excel(file_path)

                # Iterate over rows using `iterrows`
                print("Iterating over rows:")
                for index, row in df.iterrows():
                    print(f"Row {index}: {row.to_dict()}")
                    msg_data = row.to_dict()
                    payload = json.dumps({
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        "to": f"91{msg_data['To Number']}",
                        "type": "template",
                        "template": {
                            "name": "hotel",
                            "language": {
                                "code": "en"
                            },
                            "components": [
                                {
                                    "type": "header",
                                    "parameters": [
                                        {
                                            "type": "image",
                                            "image": {
                                                "link": image_url
                                            }
                                        }
                                    ]
                                },
                                {
                                    "type": "body",
                                    "parameters": [
                                        {
                                            "type": "text",
                                            "text": msg_data['Name']
                                        },
                                        {
                                            "type": "text",
                                            "text": "Underdog Crew"
                                        }
                                    ]
                                }
                            ]
                        }
                    })
                    headers = {
                        'Authorization': 'Bearer '+API_TOKEN,
                        'Content-Type': 'application/json',
                        'Cookie': 'ps_l=0; ps_n=0'
                    }
                    print(f"payload {payload}")
                    response = requests.request("POST", url, headers=headers, data=payload)

                    print(response.json())

                response_data = {
                    "message": "Message send successfully"
                }
                return JsonResponse(response_data, safe=False, status=200)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


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
            data = request.data
            print(f"data: {data}")
            entry = data['entry']
            changes = entry[0]['changes']
            value = changes[0]['value']
            phone_number_id = value['metadata']['phone_number_id']
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