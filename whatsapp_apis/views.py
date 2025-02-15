# Create your views here.
from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from whatsapp_apis.serializers import VerifyBusinessPhoneNumberSerializer, WhatsAppTemplateSerializer
import sys
import requests
from utils.database import MongoDB
from utils.auth import token_required
from UnderdogCrew.settings import API_KEY
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from datetime import datetime, timezone
from UnderdogCrew.settings import WABA_ID
from bson.objectid import ObjectId
from django.conf import settings



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
        

class WhatsAppTemplateView(APIView):
    @swagger_auto_schema(
        operation_description="Create WhatsApp message template",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=WhatsAppTemplateSerializer,
        responses={
            201: openapi.Response('Created', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'template_id': openapi.Schema(type=openapi.TYPE_STRING),
                            'fb_template_id': openapi.Schema(type=openapi.TYPE_STRING),
                            'name': openapi.Schema(type=openapi.TYPE_STRING),
                            'status': openapi.Schema(type=openapi.TYPE_STRING)
                        }
                    )
                }
            )),
            400: 'Bad Request',
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def post(self, request, current_user_id, current_user_email):
        try:
            db = MongoDB()
            
            # Validate data using serializer
            serializer = WhatsAppTemplateSerializer(data=request.data)
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            # Check if template name already exists for this user
            existing_template = db.find_document('whatsapp_templates', {
                'user_id': current_user_id,
                'name': validated_data['name']
            })

            if existing_template:
                return JsonResponse({
                    'message': 'Template name already exists'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get user's WABA ID
            user = db.find_document('users', {'_id': ObjectId(current_user_id)})
            waba_id = user.get('waba_id', WABA_ID)

            # Call Facebook Graph API
            url = f"https://graph.facebook.com/v21.0/{waba_id}/message_templates"
            headers = {
                'Content-Type': 'application/json'
            }

            fb_response = requests.post(
                url,
                headers=headers,
                json=validated_data
            )

            if fb_response.status_code != 200:
                return JsonResponse({
                    'message': 'Facebook API error',
                    'error': fb_response.json()
                }, status=status.HTTP_400_BAD_REQUEST)

            fb_data = fb_response.json()

            # Create template document
            template_data = {
                'user_id': current_user_id,
                'waba_id': waba_id,
                'fb_template_id': fb_data.get('id'),
                'name': validated_data['name'],
                'language': validated_data['language'],
                'category': validated_data['category'],
                'components': validated_data['components'],
                'status': fb_data.get('status', 'PENDING'),
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }

            template_id = db.create_document('whatsapp_templates', template_data)

            return JsonResponse({
                'status': 'success',
                'message': 'Template created successfully',
                'data': {
                    'template_id': str(template_id),
                    'fb_template_id': fb_data.get('id'),
                    'name': template_data['name'],
                    'status': template_data['status']
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_description="Get all WhatsApp message templates",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                    ),
                }
            )),
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def get(self, current_user_id, current_user_email):
        try:
            db = MongoDB()
            
            # Get all templates for the user
            templates = db.find_documents('whatsapp_templates', {
                'user_id': current_user_id
            })

            templates_data = []
            for template in templates:
                templates_data.append({
                    'id': str(template['_id']),
                    'name': template['name'],
                    'language': template['language'],
                    'category': template['category'],
                    'components': template['components'],
                    'status': template['status'],
                    'created_at': template['created_at'].isoformat(),
                    'updated_at': template['updated_at'].isoformat()
                })

            return JsonResponse({
                'status': 'success',
                'message': 'Templates retrieved successfully',
                'data': templates_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)