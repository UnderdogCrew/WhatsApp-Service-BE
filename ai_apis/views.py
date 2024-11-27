# Create your views here.
import datetime

from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
import sys
import requests
import json
from UnderdogCrew.settings import API_KEY
import pandas as pd


'''
    API for login the user in portal
    request: phone number to send the otp on number
'''
API_TOKEN = API_KEY


class SendMessage(APIView):
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