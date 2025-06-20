# Create your views here.
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse, HttpResponse
from whatsapp_apis.serializers import VerifyBusinessPhoneNumberSerializer, WhatsAppTemplateSerializer, WhatsAppTemplateEditSerializer
import sys
import requests
from utils.database import MongoDB
from utils.auth import token_required, decode_token
from UnderdogCrew.settings import API_KEY, FACEBOOK_APP_ID, WABA_ID
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from datetime import datetime, timezone
from bson.objectid import ObjectId
import pytz




def format_date(date_str, date_format="%d/%m/%Y"):
    # Convert string to date object
    if isinstance(date_str, str):
        given_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").date()
    elif isinstance(date_str, datetime):
        given_date = date_str.date()
    
    today = datetime.today().date()
    # Calculate the difference in days
    delta_days = (today - given_date).days

    if delta_days == 0:
        return date_str.strftime("%H:%M")  # Weekday name (Monday, Tuesday, etc.)
    elif delta_days == 1:
        return "Yesterday"
    elif 2 <= delta_days <= 7:
        return given_date.strftime("%A")  # Weekday name (Monday, Tuesday, etc.)
    else:
        return given_date.strftime(date_format)  # Default format dd/mm/yyyy


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
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {API_KEY}'
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

    @swagger_auto_schema(
        operation_description="Delete a WhatsApp message template by ID",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'template_name',
                openapi.IN_QUERY,
                description="Name of the template to delete",
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
                }
            )),
            400: 'Bad Request',
            401: 'Unauthorized',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def delete(self, request, current_user_id, current_user_email):
        try:
            template_name = request.query_params.get('template_name')
            if not template_name:
                return JsonResponse({
                    'message': 'template_name is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            db = MongoDB()
            
            # Get user's WABA ID
            user = db.find_document('users', {'_id': ObjectId(current_user_id)})
            waba_id = user.get('waba_id', WABA_ID)

            url = f"https://graph.facebook.com/v21.0/{waba_id}/message_templates?name={template_name}"

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {API_KEY}'
            }

            payload = {}

            response = requests.request("DELETE", url, headers=headers, data=payload)
            print(response.text)

            if response.status_code == 200:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Template deleted successfully'
                }, status=status.HTTP_200_OK)
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Template not found or not deleted'
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_description="Edit a WhatsApp message template",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'template_id',
                openapi.IN_QUERY,
                description="Facebook template ID to edit",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=WhatsAppTemplateEditSerializer,
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                }
            )),
            400: 'Bad Request',
            401: 'Unauthorized',
            403: 'Forbidden - Template cannot be edited',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def put(self, request, current_user_id, current_user_email):
        try:
            template_id = request.query_params.get('template_id')
            if not template_id:
                return JsonResponse({
                    'message': 'template_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Use the serializer for validation
            serializer = WhatsAppTemplateEditSerializer(data=request.data)
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            category = validated_data.get('category')
            components = validated_data.get('components')

            db = MongoDB()
            
            # Get user's API key
            user = db.find_document('users', {'_id': ObjectId(current_user_id)})
            if not user:
                return JsonResponse({
                    'message': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            api_key = user.get('api_key')
            
            # First, get the current template to check its status
            get_url = f"https://graph.facebook.com/v23.0/{template_id}"
            get_headers = {
                'Authorization': f'Bearer {api_key}'
            }
            
            get_response = requests.get(get_url, headers=get_headers)
            
            if get_response.status_code != 200:
                return JsonResponse({
                    'message': 'Template not found or access denied',
                    'error': get_response.json() if get_response.content else 'No response content'
                }, status=status.HTTP_404_NOT_FOUND)
            
            template_data = get_response.json()
            template_status = template_data.get('status')
            
            # Check if template can be edited
            editable_statuses = ['APPROVED', 'REJECTED', 'PAUSED']
            if template_status not in editable_statuses:
                return JsonResponse({
                    'message': f'Template with status "{template_status}" cannot be edited. Only templates with status APPROVED, REJECTED, or PAUSED can be edited.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Check if trying to edit category of an approved template
            if template_status == 'APPROVED' and category and category != template_data.get('category'):
                return JsonResponse({
                    'message': 'Cannot edit category of an approved template'
                }, status=status.HTTP_403_FORBIDDEN)

            # Prepare the edit request body
            edit_data = {}
            if category:
                edit_data['category'] = category
            if components:
                edit_data['components'] = components

            # Call Facebook Graph API to edit template
            edit_url = f"https://graph.facebook.com/v23.0/{template_id}"
            edit_headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }

            edit_response = requests.post(
                edit_url,
                headers=edit_headers,
                json=edit_data
            )

            if edit_response.status_code != 200:
                return JsonResponse({
                    'message': 'Failed to edit template',
                    'error': edit_response.json() if edit_response.content else 'No response content'
                }, status=status.HTTP_400_BAD_REQUEST)

            fb_response_data = edit_response.json()

            # Update local database record if exists
            local_template = db.find_document('whatsapp_templates', {
                'user_id': current_user_id,
                'fb_template_id': template_id
            })
            
            if local_template:
                update_data = {
                    'updated_at': datetime.now(timezone.utc)
                }
                if category:
                    update_data['category'] = category
                if components:
                    update_data['components'] = components
                
                db.update_document(
                    'whatsapp_templates',
                    {'_id': local_template['_id']},
                    update_data
                )

            return JsonResponse({
                'status': 'success',
                'message': 'Template edited successfully',
                'success': fb_response_data.get('success', True),
                'template_id': template_id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CustomersView(APIView):

    @swagger_auto_schema(
        operation_description="Get all the customers list",
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
            ),
            openapi.Parameter(
                "name",
                openapi.IN_QUERY,
                description="name for filtering data",
                type=openapi.TYPE_STRING,
                required=False,
            )
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
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            customer_details = []
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
            # Parse optional query parameters
            start_date = request.query_params.get("start_date", None)
            end_date = request.query_params.get("end_date", None)
            skip = int(request.query_params.get("skip", 0))
            limit = int(request.query_params.get("limit", 20))
            name_search = request.query_params.get("name", None)  # New parameter for name search

            # Validate and process date formats
            if start_date:
                try:
                    start_date_gmt = datetime.strptime(start_date, "%Y-%m-%d")

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
                    end_date_gmt = datetime.strptime(end_date, "%Y-%m-%d")
                    end_date_gmt = end_date_gmt.replace(hour=23, minute=59, second=59, microsecond=59)

                    # Localize to Asia/Kolkata timezone
                    kolkata_timezone = pytz.timezone("Asia/Kolkata")
                    end_date = kolkata_timezone.localize(end_date_gmt)
                except ValueError:
                    return JsonResponse(
                        {"message": "Invalid end_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            
            # Build query filter based on dates and name
            query_filter = {"user_id": user_id, "status": 1}
            if start_date:
                query_filter["created_at"] = {"$gte": start_date}
            if end_date:
                if "created_at" in query_filter:
                    query_filter["created_at"]["$lte"] = end_date
                else:
                    query_filter["created_at"] = {"$lte": end_date}
            if name_search:  # Add name search to the query filter
                query_filter["name"] = {"$regex": name_search, "$options": "i"}  # Case-insensitive search
            
            print(f"query filter: {query_filter}")
            # Fetch data from database
            sort_order = [("_id", -1)]  # Sorting in descending order
            skip_count = skip
            limit_count = limit

            customer_data = db.find_documents(collection_name="customers", query=query_filter, skip=skip_count, limit=limit_count, sort=sort_order)
            customer_count = db.find_documents_count(collection_name="customers", query=query_filter)
            for _customer in customer_data:
                customer_details.append(
                    {
                        "name": _customer['name'],
                        "number": _customer['number'],
                        "id": str(_customer['_id']),
                    }
                )

            if len(customer_details) > 0:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Customer retrieved successfully',
                    'data': customer_details,
                    "count": customer_count
                }, status=status.HTTP_200_OK)
            else:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Customer not Found',
                    'data': customer_details,
                    "count": customer_count
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


class CustomersChatLogs(APIView):

    @swagger_auto_schema(
        operation_description="Get all the customers list",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                "number",
                openapi.IN_QUERY,
                description="number of the user for whom need to fetch the history",
                type=openapi.TYPE_STRING,
                required=True,
            )
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
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        try:
            customer_chat_details = []
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
            
            # Build query filter based on dates and name
            number = request.query_params.get("number", None)
            if number is None:
                return JsonResponse({"message": "Number is invalid"}, status=422)
            
            query_filter = {"user_id": user_id, "number": f"91{number}"}
            print(f"query filter: {query_filter}")
            # Fetch data from database
            customer_query = {
                "number": int(number)
            }
            sort_order = [("_id", 1)]  # Sorting in descending order

            customer_details = db.find_document(collection_name="customers", query=customer_query)

            # if customer_details is None:
            #     return JsonResponse({"message": "Number is invalid"}, status=422)

            customer_chat_data = db.find_documents(collection_name="whatsapp_message_logs", query=query_filter, sort=sort_order)
            for _customer in customer_chat_data:
                if _customer['message_status'] in ['read', 'delivered', 'sent', 'error', 'failed']:
                    msg_type = 1
                else:
                    msg_type = 2

                def convert_to_ist(timestamp):
                    if timestamp is None:
                        return None
                    # If timestamp is an integer (Unix timestamp)
                    if isinstance(timestamp, (int, float)):
                        timestamp = datetime.fromtimestamp(timestamp, pytz.UTC)
                    # If timestamp doesn't have timezone info, assume UTC
                    elif isinstance(timestamp, datetime) and timestamp.tzinfo is None:
                        timestamp = pytz.UTC.localize(timestamp)
                    # Convert to IST
                    return timestamp.astimezone(pytz.timezone('Asia/Kolkata'))

                customer_chat_details.append(
                    {
                        "number": _customer['number'],
                        "message": _customer['message'],
                        "created_at": convert_to_ist(_customer.get('created_at')),
                        "updated_at": convert_to_ist(_customer.get('updated_at')),
                        "sent_at": convert_to_ist(_customer.get('sent_at')),
                        "read_at": convert_to_ist(_customer.get('read_at')),
                        "status": _customer['message_status'],
                        "msg_type": msg_type
                    }
                )

            customers = {
                "name": customer_details['name'] if customer_details is not None else f"{number}",
                "number": str(customer_details['number']) if customer_details is not None else f"{number}"
            }

            if len(customer_chat_details) > 0:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Customer retrieved successfully',
                    'data': customer_chat_details,
                    "customer": customers
                }, status=status.HTTP_200_OK)
            else:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Customer not Found',
                    'data': customer_chat_details
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UniqueChatList(APIView):

    @swagger_auto_schema(
        operation_description="Get the latest message for each unique user number, including customer names",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Searched text based on name",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'chat_list': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT)
                    )
                }
            )),
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def get(self, request, current_user_id=None, current_user_email=None):
        try:
            db = MongoDB()
            token = request.headers.get('Authorization')

            if not token or not token.startswith('Bearer '):
                return JsonResponse({"message": "Authorization token is missing or invalid"}, status=401)

            token = token.split(' ')[1]
            user_info = decode_token(token)

            if not isinstance(user_info, dict) or 'user_id' not in user_info:
                return JsonResponse({"message": "Invalid token or user information could not be retrieved"}, status=401)

            user_id = user_info['user_id']
            print(f"user_id: {user_id}")

            match_query = {
                "user_id": user_id,
                "$expr": {
                    "$eq": [{"$strLenCP": "$number"}, 12]
                }
            }

            # Aggregation Query to Get Unique Numbers with Latest Messages and Join with Customers
            search_text = request.query_params.get('search', '').strip()

            pipeline = [
                # First lookup customers to get matching names
                {"$lookup": {
                    "from": "customers",
                    "let": { 
                        "phone_str": {
                            "$replaceAll": {
                                "input": {"$substr": ["$number", 2, -1]},
                                "find": " ",
                                "replacement": ""
                            }
                        }
                    },
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    '$and': [
                                        {
                                            '$eq': [
                                            '$number',
                                            {
                                                '$toDouble': {
                                                '$replaceAll': {
                                                    'input': '$$phone_str',
                                                    'find': ' ',
                                                    'replacement': ''
                                                }
                                                }
                                            }
                                            ]
                                        },
                                        {
                                            '$eq': ['$user_id', user_id]
                                        }
                                    ]
                                },
                                **({'name': {'$regex': search_text, '$options': 'i'}} if search_text else {})
                            }
                        }
                    ],
                    "as": "customer_info"
                }},
                # Only keep messages that have matching customers if searching
                {"$match": {
                    **match_query,
                    **({'customer_info': {'$ne': []}} if search_text else {})
                }},
                {"$sort": {"updated_at": -1}},
                {"$group": {
                    "_id": "$number",
                    "last_message": {"$first": "$message"},
                    "last_message_time": {"$first": "$updated_at"},
                    "message_status": {"$first": "$message_status"},
                    "template_name": {"$first": "$template_name"},
                    "sent_at": {"$first": "$sent_at"},
                    "delivered_at": {"$first": "$delivered_at"},
                    "failed_at": {"$first": "$failed_at"},
                    "customer_info": {"$first": "$customer_info"}
                }},
                {"$unwind": {
                    "path": "$customer_info",
                    "preserveNullAndEmptyArrays": True
                }},
                {"$project": {
                    "profile_name": {"$ifNull": ["$customer_info.name", "$_id"]},
                    "last_message": 1,
                    "last_message_time": 1,
                    "message_status": 1,
                    "template_name": 1,
                    "sent_at": 1,
                    "delivered_at": 1,
                    "failed_at": 1,
                    "msg_type": {
                        "$cond": {
                            "if": {"$in": ["$message_status", ["read", "delivered", "sent", "error"]]},
                            "then": 1,
                            "else": 2
                        }
                    }
                }},
                {"$sort": {"last_message_time": -1}}
            ]

            print(f"pipeline: {pipeline}")

            chat_list_data = db.aggregate(collection_name="whatsapp_message_logs", pipeline=pipeline)
            chat_list = []
            
            # Add timezone conversion
            ist_timezone = pytz.timezone('Asia/Kolkata')

            for chat in chat_list_data:
                msg_type = chat.get("msg_type", 2)
                profile_name = chat.get("profile_name", "Unknown")
                
                # Convert last_message_time to IST
                last_message_time = chat.get("last_message_time")
                if last_message_time:
                    if not last_message_time.tzinfo:
                        # If timestamp is naive, assume it's UTC
                        last_message_time = pytz.utc.localize(last_message_time)
                    # Convert to IST
                    last_message_time = last_message_time.astimezone(ist_timezone)

                
                changed_date = format_date(date_str=last_message_time)

                
                if profile_name is None or profile_name == "nan" or profile_name == "NaN" or profile_name == "":
                    pass
                else:
                    chat_list.append({
                        "number": chat.get("_id")[2:] if chat.get("_id") else "",
                        "profile_name": profile_name,
                        "last_message": chat.get("last_message", ""),
                        "last_message_time": last_message_time,
                        "date": changed_date,
                        "status": chat.get("message_status", ""),
                        "template_name": chat.get("template_name", ""),
                        "sent_at": chat.get("sent_at"),
                        "delivered_at": chat.get("delivered_at"),
                        "unread_count": 0 if msg_type == 1 else 1,
                        "failed_at": chat.get("failed_at"),
                        "msg_type": chat.get("msg_type", 2)  # Default to 2 if not found
                    })

            if len(chat_list) > 0:
                return JsonResponse({
                    'status': 'success',
                    'message': 'Unique chat list retrieved successfully',
                    'chat_list': chat_list
                }, status=status.HTTP_200_OK)
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Unique chat list not found',
                    'chat_list': []
                }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FacebookFileUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    @swagger_auto_schema(
        operation_description="Upload a file to Facebook for WhatsApp templates",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'file',
                openapi.IN_FORM,
                description="File to upload",
                type=openapi.TYPE_FILE,
                required=True
            ),
        ],
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'file_handle': openapi.Schema(type=openapi.TYPE_STRING),
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
            if 'file' not in request.FILES:
                return JsonResponse({
                    'message': 'No file provided'
                }, status=status.HTTP_400_BAD_REQUEST)

            file = request.FILES['file']
            
            # Validate file type
            allowed_types = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'video/mp4']
            if file.content_type not in allowed_types:
                return JsonResponse({
                    'message': f'Invalid file type. Allowed types: {", ".join(allowed_types)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Step 1: Start upload session
            session_response = requests.post(
                f"https://graph.facebook.com/v22.0/{FACEBOOK_APP_ID}/uploads",
                params={
                    'access_token': API_KEY,
                    'file_length': file.size,
                    'file_type': file.content_type,
                    'file_name': file.name
                }
            )

            if session_response.status_code != 200:
                return JsonResponse({
                    'message': 'Failed to initiate upload session',
                    'error': session_response.json()
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            upload_session_id = session_response.json()['id'].split(':')[1]

            # Step 2: Upload the file
            headers = {
                'Authorization': f'OAuth {API_KEY}',
                'file_offset': '0'
            }

            upload_response = requests.post(
                f"https://graph.facebook.com/v22.0/upload:{upload_session_id}",
                headers=headers,
                data=file.read()
            )

            print(f"upload_response: {upload_response}")

            if upload_response.status_code != 200:
                return JsonResponse({
                    'message': 'Failed to upload file',
                    'error': upload_response.json()
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            file_handle = upload_response.json().get('h')

            return JsonResponse({
                'status': 'success',
                'file_handle': file_handle,
                'upload_session_id': upload_session_id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_description="Resume an interrupted file upload",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'upload_session_id',
                openapi.IN_QUERY,
                description="Upload session ID",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'file',
                openapi.IN_FORM,
                description="File to upload",
                type=openapi.TYPE_FILE,
                required=True
            ),
        ],
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'file_handle': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request',
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def put(self, request, current_user_id, current_user_email):
        try:
            upload_session_id = request.GET.get('upload_session_id')
            if not upload_session_id:
                return JsonResponse({
                    'message': 'Upload session ID is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get current offset
            offset_response = requests.get(
                f"https://graph.facebook.com/v22.0/upload:{upload_session_id}",
                headers={'Authorization': f' {API_KEY}'}
            )

            if offset_response.status_code != 200:
                return JsonResponse({
                    'message': 'Failed to get upload offset',
                    'error': offset_response.json()
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            file_offset = offset_response.json().get('file_offset', 0)

            # Resume upload
            file = request.FILES.get('file')
            if not file:
                return JsonResponse({
                    'message': 'No file provided'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Seek to the offset position
            file.seek(file_offset)

            headers = {
                'Authorization': f'OAuth {API_KEY}',
                'file_offset': str(file_offset)
            }

            upload_response = requests.post(
                f"https://graph.facebook.com/v22.0/upload:{upload_session_id}",
                headers=headers,
                data=file.read()
            )

            if upload_response.status_code != 200:
                return JsonResponse({
                    'message': 'Failed to resume upload',
                    'error': upload_response.json()
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            file_handle = upload_response.json().get('h')

            # Update upload record in database
            db = MongoDB()
            db.update_document(
                'facebook_uploads',
                {'upload_session_id': upload_session_id},
                {
                    'file_handle': file_handle,
                    'updated_at': datetime.now(timezone.utc),
                    'status': 'completed'
                }
            )

            return JsonResponse({
                'status': 'success',
                'file_handle': file_handle
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
