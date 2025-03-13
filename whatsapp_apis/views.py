# Create your views here.
from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from whatsapp_apis.serializers import VerifyBusinessPhoneNumberSerializer, WhatsAppTemplateSerializer
import sys
import requests
from utils.database import MongoDB
from utils.auth import token_required, decode_token
from UnderdogCrew.settings import API_KEY
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from datetime import datetime, timezone
from UnderdogCrew.settings import WABA_ID
from bson.objectid import ObjectId
from django.conf import settings
import pytz



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

            if customer_details is None:
                return JsonResponse({"message": "Number is invalid"}, status=422)

            customer_chat_data = db.find_documents(collection_name="whatsapp_message_logs", query=query_filter, sort=sort_order)
            for _customer in customer_chat_data:
                if _customer['message_status'] in ['read', 'delivered', 'sent', 'error']:
                    msg_type = 1
                else:
                    msg_type = 2

                customer_chat_details.append(
                    {
                        "number": _customer['number'],
                        "message": _customer['message'],
                        "created_at": _customer['created_at'],
                        "updated_at": _customer['updated_at'] if "updated_at" in _customer else None,
                        "sent_at": _customer['sent_at'] if "sent_at" in _customer else None,
                        "read_at": _customer['read_at'] if "read_at" in _customer else None,
                        "status": _customer['message_status'],
                        "msg_type": msg_type
                    }
                )

            customers = {
                "name": customer_details['name'],
                "number": str(customer_details['number'])
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
                                    "$eq": [
                                        "$number",
                                        {
                                            "$toDouble": {
                                                "$replaceAll": {
                                                    "input": "$$phone_str",
                                                    "find": " ",
                                                    "replacement": ""
                                                }
                                            }
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

            chat_list_data = db.aggregate(collection_name="whatsapp_message_logs", pipeline=pipeline)
            chat_list = []
            for chat in chat_list_data:
                msg_type = chat.get("msg_type", 2)
                profile_name = chat.get("profile_name", "Unknown")
                if profile_name is None or profile_name == "nan" or profile_name == "NaN" or profile_name == "":
                    pass
                else:
                    chat_list.append({
                        "number": chat.get("_id")[2:] if chat.get("_id") else "",  # Get all digits after first 2
                        "profile_name": chat.get("profile_name", "Unknown"),
                        "last_message": chat.get("last_message", ""),
                        "last_message_time": chat.get("last_message_time"),
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
