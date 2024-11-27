# Create your views here.
import datetime

from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
import sys
import requests
import json
from UnderdogCrew.settings import API_KEY


'''
    API for login the user in portal
    request: phone number to send the otp on number
'''
API_TOKEN = API_KEY


class SendMessage(APIView):
    def post(self, request):
        try:
            url = "https://graph.facebook.com/v18.0/450885871446042/messages"
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
            elif "to" not in request_data:
                response_data = {
                    "message": "to is missing",
                }
                return JsonResponse(response_data, safe=False, status=422)
            else:
                text = request_data['text']
                name = request_data['name']
                image_url = request_data['image_url'] if "image_url" in request_data else ""
                to_msg = request_data['to']

                payload = json.dumps({
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_msg,
                    "type": "template",
                    "template": {
                        "name": "media_template",
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
                                        "text": text
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