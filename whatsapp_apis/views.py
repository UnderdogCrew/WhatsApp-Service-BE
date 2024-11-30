# Create your views here.
from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from whatsapp_apis.serializer import VerifyBusinessPhoneNumberSerializer
import sys
import requests
from UnderdogCrew.settings import API_KEY
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


# Function to check phone number and country code
def check_phone_number(data, phone_number, country_code):
    for record in data.get('data', []):
        display_phone_number = record.get('display_phone_number', '').replace(" ", "")
        phone_number = phone_number.replace(" ", "")
        expected_number = f"{country_code}{phone_number}"
        print(expected_number)
        if display_phone_number == expected_number:
            return True, record
    return False, {}



# APIView with serializer integration
class VerifyBusinessPhoneNumber(APIView):
    @swagger_auto_schema(
        operation_description="Verify a business phone number",
        request_body=VerifyBusinessPhoneNumberSerializer,
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'business_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'is_verified': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'phone_number': openapi.Schema(type=openapi.TYPE_STRING),
                    'country_code': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            # Validate incoming data with the serializer
            serializer = VerifyBusinessPhoneNumberSerializer(data=request.data)
            if serializer.is_valid():
                # Access validated data
                validated_data = serializer.validated_data
                phone_number = validated_data['phone_number']
                country_code = validated_data['country_code']

                url = "https://graph.facebook.com/v21.0/236353759566806/phone_numbers?fields=id,is_official_business_account,display_phone_number,verified_name"

                payload = {}
                headers = {
                    'Authorization': f'Bearer {API_KEY}'
                }

                response = requests.request("GET", url, headers=headers, data=payload)
                data = response.json()
                # Check and print result
                is_present, entry = check_phone_number(data, phone_number, country_code)
                print("Is the phone number present?", is_present)
                if is_present is True:
                    business_id = entry['id']
                else:
                    business_id = ""
                # Process the request further with validated data
                response_data = {
                    "message": "Message sent successfully",
                    "business_id": business_id,
                    "is_verified": is_present,
                    "phone_number": phone_number,
                    "country_code": country_code
                }
                return JsonResponse(response_data, safe=False, status=200)
            else:
                # If validation fails, return error response
                return JsonResponse({"errors": serializer.errors}, safe=False, status=400)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "Something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)


class MessageTemplates(APIView):
    @swagger_auto_schema(
        operation_description="Retrieve message templates",
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                }
            )),
            400: 'Template not found',
            500: 'Internal Server Error'
        }
    )
    def get(self, request):
        try:
            url = "https://graph.facebook.com/v21.0/236353759566806/message_templates"

            payload = {}
            headers = {
                'Authorization': f'Bearer {API_KEY}'
            }
            response = requests.request("GET", url, headers=headers, data=payload)
            print(response.text)
            if response.status_code == 200:
                data = response.json()
                response_data = {
                    "message": "Message sent successfully",
                    "data": [entry for entry in data["data"] if entry.get("name") != "hello_world"]
                }
                return JsonResponse(response_data, safe=False, status=200)
            else:
                # If validation fails, return error response
                return JsonResponse({"errors": "Template not found"}, safe=False, status=400)
        except Exception as ex:
            print("Error on line {}".format(sys.exc_info()[-1].tb_lineno), type(ex).__name__, ex)
            error = {
                "message": "Something went wrong"
            }
            return JsonResponse(error, safe=False, status=500)