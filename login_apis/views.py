from rest_framework.views import APIView
from django.http import  JsonResponse
from rest_framework import status
from django.contrib.auth.hashers import make_password, check_password
from drf_yasg import openapi
from bson import ObjectId
from drf_yasg.utils import swagger_auto_schema
from utils.database import MongoDB
from utils.auth import generate_tokens, token_required, decode_token, current_dollar_price
from .serializers import SignupSerializer, LoginSerializer, FileUploadSerializer, FileUploadResponseSerializer, BusinessDetailsSerializer
from utils.s3_helper import S3Helper
from .utils import get_file_extension, validate_file
from rest_framework.parsers import MultiPartParser, FormParser
from utils.twilio_otp import generate_otp, send_otp
from datetime import datetime, timezone
import twilio
from UnderdogCrew.settings import SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD ,SECRET_KEY
import re
import jwt
import random

# Create your views here.

class SignupView(APIView):
    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='User email'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='User password'),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING, description='First name'),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING, description='Last name'),
                'business_number': openapi.Schema(type=openapi.TYPE_STRING, description='Business number'),
                'business_id': openapi.Schema(type=openapi.TYPE_STRING, description='Business ID (optional)'),
            },
            required=['email', 'password', 'first_name', 'last_name', 'business_number']
        ),
        responses={
            201: openapi.Response('Created', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'user': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'tokens': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'business_verified': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                }
            )),
            400: 'Bad Request',
            409: 'Conflict',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            # Initialize MongoDB connection
            db = MongoDB()
            serializer = SignupSerializer(data=request.data)
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            # Check if user already exists by email
            if db.find_document('users', {'email': validated_data['email']}):
                return JsonResponse({
                    'message': 'Email already exists'
                }, safe=False, status=status.HTTP_409_CONFLICT)

            # Check if business_number already exists
            if db.find_document('users', {'business_number': validated_data['business_number']}):
                return JsonResponse({
                    'message': 'Business number already exists'
                }, safe=False, status=status.HTTP_409_CONFLICT)

            # Generate a 12-digit account ID (similar to AWS format)
            account_id = ''.join([str(random.randint(0, 9)) for _ in range(12)])

            # Create user with account_id
            user_data = {
                'email': validated_data['email'],
                'password': make_password(validated_data['password']),
                'base_encoded_password': validated_data['password'],
                'first_name': validated_data['first_name'],
                'last_name': validated_data['last_name'],
                'business_number': validated_data['business_number'],
                'business_id': validated_data.get('business_id', ''),
                'default_credit': 1000,
                'is_email_verified': False,
                'status': 'active',
                'is_active': True,
                'account_id': account_id
            }

            user_id = db.create_document('users', user_data)
            access_token, refresh_token = generate_tokens(user_id, validated_data['email'])

            # Check if WhatsApp business details exist
            business_verified = 0  # Default to 0 (no business details)
            return JsonResponse({
                'status': 'success',
                'message': 'User created successfully',
                'data': {
                    'user': {
                        'id': user_id,
                        'email': validated_data['email'],
                        'first_name': validated_data['first_name'],
                        'last_name': validated_data['last_name'],
                        'business_id': user_data['business_id'],
                        'is_email_verified': user_data['is_email_verified'] if "is_email_verified" in user_data else False,
                        'account_id': user_data['account_id'],
                        'status': user_data['status'],
                        'is_active': user_data['is_active']
                    },
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    },
                    'business_verified': business_verified  # Set to 0
                }
            }, safe=False, status=status.HTTP_201_CREATED)
        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, safe=False, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(APIView):
    @swagger_auto_schema(
        operation_description="Login user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='User email'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='User password'),
            },
            required=['email', 'password']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'user': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'tokens': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'business_verified': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    ),
                }
            )),
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            serializer = LoginSerializer(data=request.data)
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            db = MongoDB()
            user = db.find_document('users', {'email': validated_data['email']})

            if user and check_password(validated_data['password'], user['password']):
                access_token, refresh_token = generate_tokens(str(user['_id']), validated_data['email'])
                
                # Check if WhatsApp business details exist
                if 'whatsapp_business_details' in user:
                    if user['whatsapp_business_details'].get('verified', False):
                        business_verified = 2  # Verified business details
                    else:
                        business_verified = 1  # Business details present but not verified
                else:
                    business_verified = 0  # No business details

                return JsonResponse({
                    'status': 'success',
                    'message': 'Login successful',
                    'data': {
                        'user': {
                            'id': str(user['_id']),
                            'email': user['email'],
                            'first_name': user['first_name'],
                            'last_name': user['last_name'],
                            'is_email_verified': user.get('is_email_verified', False),
                            'account_id': user.get('account_id', ''),
                            'is_active': user.get('is_active', True)
                        },
                        'tokens': {
                            'access': access_token,
                            'refresh': refresh_token
                        },
                        'business_verified': business_verified  # Set based on business details
                    }
                }, safe=False, status=status.HTTP_200_OK)
            return JsonResponse({
                'message': 'Invalid credentials'
            }, safe=False, status=status.HTTP_401_UNAUTHORIZED)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, safe=False, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FileUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    
    @swagger_auto_schema(
        operation_description="Upload file to S3 bucket",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=FileUploadSerializer,
        responses={
            200: FileUploadResponseSerializer,
            400: 'Bad Request',
            401: 'Unauthorized',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def post(self, request, current_user_id, current_user_email):
        try:
            db = MongoDB()
            serializer = FileUploadSerializer(data=request.data)
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            file = serializer.validated_data['file']
                        
            # Get user details and check status
            user = db.find_document('users', {
                '_id': ObjectId(current_user_id),
            })
            
            if not user:
                return JsonResponse({
                    'message': 'Active user not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Validate file
            is_valid, file_type, mime_type = validate_file(file)
            if not is_valid:
                return JsonResponse({
                    'message': f'Invalid file type: {mime_type}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get file extension and determine folder
            file_extension = get_file_extension(mime_type)
            folder = f"{current_user_id}/{file_type}s"

            # Upload to S3
            s3_helper = S3Helper()
            file_url = s3_helper.upload_file(
                file_obj=file,
                folder_name=folder,
                file_extension=file_extension,
                content_type=mime_type
            )

            if not file_url:
                return JsonResponse({
                    'message': 'Failed to upload file'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return JsonResponse({
                'status': 'success',
                'message': 'File uploaded successfully',
                'data': {
                    'file_url': file_url,
                    'file_type': file_type,
                    'file_name': file.name,
                    'file_size': file.size,
                    'mime_type': mime_type,
                    'uploaded_by': user['email']
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class OTPGenerate(APIView):
    @swagger_auto_schema(
        operation_description="Send OTP to phone number",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'phone_number': openapi.Schema(type=openapi.TYPE_STRING, description='Phone number with country code'),
            },
            required=['phone_number']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            phone_number = request.data.get('phone_number')
            # Validate phone number format
            if not phone_number or not re.match(r'^\+\d{1,3}\d{10,15}$', phone_number):
                return JsonResponse({
                    'message': 'Phone number must include country code and be followed by the number'
                }, status=status.HTTP_400_BAD_REQUEST)

            db = MongoDB()
            otp = generate_otp()
            
            # Store OTP in MongoDB with timestamp
            otp_data = {
                'phone_number': phone_number,
                'otp': otp,
                'created_at': datetime.now(timezone.utc),
                'is_verified': False
            }
            # Send OTP via Twilio
            send_otp(phone_number, otp)

            db.create_document('otps', otp_data)

            return JsonResponse({
                'status': 'success',
                'message': 'OTP sent successfully'
            }, status=status.HTTP_200_OK)
        except twilio.base.exceptions.TwilioRestException as e:
            return JsonResponse({
                'message': str(e.msg)
            })
        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class OTPVerify(APIView):
    @swagger_auto_schema(
        operation_description="Verify OTP",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'phone_number': openapi.Schema(type=openapi.TYPE_STRING, description='Phone number with country code'),
                'otp': openapi.Schema(type=openapi.TYPE_STRING, description='OTP received'),
            },
            required=['phone_number', 'otp']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            phone_number = request.data.get('phone_number')
            input_otp = request.data.get('otp')

            # Validate phone number format
            if not phone_number or not re.match(r'^\+\d{1,3}\d{10,15}$', phone_number):
                return JsonResponse({
                    'message': 'Phone number must include country code and be followed by the number'
                }, status=status.HTTP_400_BAD_REQUEST)

            if not phone_number or not input_otp:
                return JsonResponse({
                    'message': 'Phone number and OTP are required'
                }, status=status.HTTP_400_BAD_REQUEST)

            db = MongoDB()
            
            # Find the latest OTP for this phone number
            otp_record = db.find_documents('otps', {
                'phone_number': phone_number,
                'is_verified': False
            }, sort=[('created_at', -1)],limit=1)

            if not otp_record:
                return JsonResponse({
                    'message': 'No OTP found for this number'
                }, status=status.HTTP_404_NOT_FOUND)
        
            # Check if OTP is expired (5 minutes validity)
            time_diff = datetime.now(timezone.utc) - otp_record[0]['created_at'].astimezone(timezone.utc)
            if time_diff.total_seconds() > 300:  # 5 minutes
                return JsonResponse({
                    'message': 'OTP has expired'
                }, status=status.HTTP_400_BAD_REQUEST)

            if str(otp_record[0]['otp']) != str(input_otp):
                return JsonResponse({
                    'message': 'Invalid OTP'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Mark OTP as verified
            db.update_document('otps', 
                {'_id': otp_record[0]['_id']}, 
                {'is_verified': True}
            )

            return JsonResponse({
                'status': 'success',
                'message': 'OTP verified successfully'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BusinessDetails(APIView):
    @swagger_auto_schema(
        operation_description="Update WhatsApp business details",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=BusinessDetailsSerializer,
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required  # Assuming you want to protect this endpoint
    def patch(self, request, current_user_id, current_user_email):
        try:
            serializer = BusinessDetailsSerializer(data=request.data)  # Validate incoming data
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            # Extract validated data
            business_details = serializer.validated_data

            db = MongoDB()

            business_details["verified"] = False
            # Update the user's WhatsApp business details
            result = db.update_document('users', 
                {'_id': ObjectId(current_user_id)}, 
                {'whatsapp_business_details': business_details}
            )

            if result.modified_count == 0:
                return JsonResponse({
                    'message': 'No changes made or user not found'
                }, status=status.HTTP_404_NOT_FOUND)

            return JsonResponse({
                'status': 'success',
                'message': 'WhatsApp business details updated successfully'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_description="Get WhatsApp business details",
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
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'whatsapp_business_details': openapi.Schema(type=openapi.TYPE_OBJECT),
                        }
                    ),
                }
            )),
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required  # Assuming you want to protect this endpoint
    def get(self, request, current_user_id, current_user_email):
        try:
            db = MongoDB()
            # Fetch the user's WhatsApp business details
            user = db.find_document('users', {'_id': ObjectId(current_user_id)})

            if not user or 'whatsapp_business_details' not in user:
                return JsonResponse({
                    'message': 'WhatsApp business details not found'
                }, status=status.HTTP_404_NOT_FOUND)

            return JsonResponse({
                'status': 'success',
                'message': 'WhatsApp business details retrieved successfully',
                'data': {
                    'whatsapp_business_details': user['whatsapp_business_details']
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class EmailVerificationView(APIView):
    @swagger_auto_schema(
        operation_description="Verify if an email is already registered",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='User email'),
            },
            required=['email']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'exists': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                }
            )),
            400: 'Bad Request',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        try:
            email = request.data.get('email')

            # Validate email format
            if not email or not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                return JsonResponse({
                    'message': 'Invalid email format'
                }, status=status.HTTP_400_BAD_REQUEST)

            db = MongoDB()
            user_exists = db.find_document('users', {'email': email})

            return JsonResponse({
                'status': 'success',
                'message': 'Email verification successful',
                'exists': user_exists is not None  # True if user exists, False otherwise
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RefreshTokenView(APIView):
    @swagger_auto_schema(
        operation_description="Refresh access token",
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
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'access_token': openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    ),
                }
            )),
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    def get(self, request):
        try:
            token = None
            if 'Authorization' in request.headers:
                auth_header = request.headers['Authorization']
                try:
                    token = auth_header.split(" ")[1]  # Extract the token
                except IndexError:
                    return JsonResponse({
                        'message': 'Invalid token format'
                    }, status=401)

            if not token:
                return JsonResponse({
                    'message': 'Token is missing'
                }, status=401)

            # Decode the refresh token
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = data['user_id']
            user_email = data['user_email']

            # Generate new access token
            access_token, _ = generate_tokens(user_id, user_email)

            return JsonResponse({
                'status': 'success',
                'message': 'Access token refreshed successfully',
                'data': {
                    'access_token': access_token
                }
            }, status=status.HTTP_200_OK)

        except jwt.ExpiredSignatureError:
            return JsonResponse({
                'message': 'Refresh token has expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminLoginView(APIView):
    @swagger_auto_schema(
        operation_description="Admin login for superadmin user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='Superadmin email'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Superadmin password'),
            },
            required=['email', 'password']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'tokens': openapi.Schema(type=openapi.TYPE_OBJECT),
                        }
                    ),
                }
            )),
            401: 'Invalid credentials',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if email == SUPERADMIN_EMAIL and check_password(password, make_password(SUPERADMIN_PASSWORD)):
            # Generate tokens for superadmin
            access_token, refresh_token = generate_tokens("superadmin", SUPERADMIN_EMAIL)
            return JsonResponse({
                'status': 'success',
                'message': 'Admin login successful',
                'data': {
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    }
                }
            }, status=status.HTTP_200_OK)

        return JsonResponse({
            'message': 'Invalid credentials'
        }, status=status.HTTP_401_UNAUTHORIZED)

class GetAllUsersView(APIView):
    @swagger_auto_schema(
        operation_description="Get all users with optional search and pagination",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="Search by first name, last name, or email", type=openapi.TYPE_STRING),
            openapi.Parameter('business_verified', openapi.IN_QUERY, description="Filter by WhatsApp business verified status (true/false)", type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('skip', openapi.IN_QUERY, description="Number of records to skip", type=openapi.TYPE_INTEGER),
            openapi.Parameter('limit', openapi.IN_QUERY, description="Number of records to return", type=openapi.TYPE_INTEGER),
        ],
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'data': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                }
            )),
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    def get(self, request):
        search = request.query_params.get('search', '')
        business_verified = request.query_params.get('business_verified', None)
        skip = int(request.query_params.get('skip', 0))
        limit = int(request.query_params.get('limit', 10))

        # Initialize MongoDB connection
        db = MongoDB()
        query = {}

        if search:
            query['$or'] = [
                {'first_name': {'$regex': search, '$options': 'i'}},
                {'last_name': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}}
            ]
        if business_verified is not None:
            query['whatsapp_business_details.verified'] = business_verified.lower() == 'true'

         # Specify projection to exclude the password field
        projection = {
            'password': 0,
            'base_encoded_password': 0 
        }

        users = db.find_documents('users', query, skip=skip, limit=limit,projection=projection)
        if not users:
            return JsonResponse({
                'message': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)

        for user in users:
            user['id'] = str(user['_id'])
            del user['_id']

        print(users)
        return JsonResponse({
            'status': 'success',
            'data': users
        }, status=status.HTTP_200_OK)

class VerifyBusinessDetailsView(APIView):
    @swagger_auto_schema(
        operation_description="Verify WhatsApp business details and set business ID",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_STRING, description='User ID to update'),
                'business_id': openapi.Schema(type=openapi.TYPE_STRING, description='Business ID to set'),
            },
            required=['user_id', 'business_id']
        ),
        responses={
            200: openapi.Response('Success', openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: 'Bad Request',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    def patch(self, request):
        try:
            user_id = request.data.get('user_id')
            business_id = request.data.get('business_id')

            # Validate user_id and business_id
            if not user_id or not business_id:
                return JsonResponse({
                    'message': 'User ID and Business ID are required'
                }, status=status.HTTP_400_BAD_REQUEST)

            db = MongoDB()
            # Find the user with the provided user_id
            user = db.find_document('users', {'_id': ObjectId(user_id)})

            if not user:
                return JsonResponse({
                    'message': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Update the user's WhatsApp business details to set verified to True and add business_id
            result = db.update_document('users', 
                {'_id': ObjectId(user['_id'])}, 
                {'whatsapp_business_details.verified': True, 'business_id': business_id}
            )

            if result.modified_count == 0:
                return JsonResponse({
                    'message': 'No changes made or user not found'
                }, status=status.HTTP_404_NOT_FOUND)

            return JsonResponse({
                'status': 'success',
                'message': 'Business details verified and updated successfully'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProfileView(APIView):
    @swagger_auto_schema(
        operation_description="Get user profile and subscription details",
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
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'user': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'subscription': openapi.Schema(type=openapi.TYPE_OBJECT),
                            'plans': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                        }
                    ),
                }
            )),
            401: 'Unauthorized',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def get(self, request, current_user_id, current_user_email):
        try:
            db = MongoDB()
            
            # Get user details
            user = db.find_document('users', {'_id': ObjectId(current_user_id)})
            if not user:
                return JsonResponse({
                    'message': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Get user's subscription
            subscription = db.find_document('subscriptions', {
                'user_email': current_user_email
            })

            # Format the response
            user_data = {
                'id': str(user['_id']),
                'email': user['email'],
                'first_name': user['first_name'],
                'last_name': user['last_name'],
                'business_number': user.get('business_number', ''),
                'business_id': user.get('business_id', ''),
                'is_email_verified': user.get('is_email_verified', False),
                'default_credit': user.get('default_credit', 0),
                'account_id': user.get('account_id', '')
            }

            subscription_data = None
            if subscription:
                # Get plan details if subscription exists
                plan = db.find_document('plans', {'planid': subscription['plan_id']})
                subscription_data = {
                    'id': str(subscription['_id']),
                    'status': subscription.get('status', ''),
                    'total_count': subscription.get('total_count', ''),
                    'has_access': subscription.get('has_access', False),
                    'plan': {
                        'planid': str(plan['planid']),
                        'planname': plan.get('planname', ''),
                        'billing_amount': plan.get('billing_amount', ''),
                    } if plan else None
                }

            return JsonResponse({
                'status': 'success',
                'message': 'Profile retrieved successfully',
                'data': {
                    'user': user_data,
                    'subscription': subscription_data
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UserBillingAPIView(APIView):
    """
    API to get user billing details from WhatsApp, Image Generation, and Text Generation logs.
    """

    @swagger_auto_schema(
        operation_description="Get total billing for a user within a date range",
        manual_parameters=[
            openapi.Parameter(
                name="Authorization",
                in_=openapi.IN_HEADER,
                description="Bearer <your_token>",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                name="start_date",
                in_=openapi.IN_QUERY,
                description="Filter records starting from this date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                name="end_date",
                in_=openapi.IN_QUERY,
                description="Filter records up to this date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description="Total billing details",
                examples={
                    "application/json": {
                        "user_id": "677fff42d9fba430631d4478",
                        "start_date": "2025-02-14",
                        "end_date": "2025-02-15",
                        "whatsapp_total": 0.125,
                        "image_total": 0.08,
                        "text_total": 0.00001335,
                        "total_price": 0.20501335
                    }
                }
            ),
            400: openapi.Response(
                description="Invalid date format",
                examples={
                    "application/json": {
                        "error": "Invalid date format. Use YYYY-MM-DD."
                    }
                }
            )
        }
    )
    @token_required  # Ensure the user is authenticated
    def get(self, request, current_user_id=None, current_user_email=None):  # Accept additional parameters
        db = MongoDB()

        # Get query parameters for start and end date
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        dollar_price = current_dollar_price()

        # Check if start_date and end_date are provided
        if not start_date or not end_date:
            return JsonResponse({"error": "Both start_date and end_date are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Convert dates to ISO format
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

            # Set time for start_date to 00:00:00
            start_date = start_date.replace(hour=0, minute=0, second=0)

            # Set time for end_date to 23:59:59
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # Build filter conditions
        filters = {"user_id": current_user_id, "created_at": {"$gte": start_date, "$lte": end_date}}

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

        # Check for invoices in the given date range
        invoice_filters = {
            "user_id": current_user_id,
            "created_at": {"$gte": start_date, "$lte": end_date}
        }
        invoices = db.find_documents('invoices', invoice_filters)
        invoice_status = "Issued"
        if invoices:
            if invoices[0].get('payment_status') == "Paid":
                invoice_status = "Paid"
        else:
            invoice_status = "Pending"
        # Fetch user details from the database
        user = db.find_document('users', {'_id': ObjectId(current_user_id)})
        account_id = user.get('account_id', '') if user else ''  # Get account_id if user exists, else empty string

        # Format billing period
        billing_period = f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}"

        return JsonResponse({
            "user_id": current_user_id,
            "billing_period": billing_period,  # Include billing period in the response
            "whatsapp_total": f"₹{round(whatsapp_total, 2)}",
            "image_total": f"₹{round(image_total, 2)}",
            "text_total": f"₹{round(text_total, 2)}",
            "total_price": f"₹{round(total_price, 2)}",
            "final_price": f"₹{round(total_price_with_tax, 2)}",
            "cgst": f"₹{round(cgst, 2)}",
            "sgst": f"₹{round(sgst, 2)}",
            "invoice_status": invoice_status,
            "payment_status": invoices[0].get('payment_status') if invoices else "Pending",
            "invoice_number": invoices[0].get('invoice_number') if invoices else "",
            "account_id": account_id
        }, status=status.HTTP_200_OK)

class UserStatusView(APIView):
    @swagger_auto_schema(
        operation_description="Get user's active status flags",
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
                    'data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'has_active_plan': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'pending_bills': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'waba_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'account_id': openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    ),
                }
            )),
            401: 'Unauthorized',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def get(self, request, current_user_id, current_user_email):
        try:
            db = MongoDB()
            
            # Get user details with specific field projection for performance
            user = db.find_document(
                'users', 
                {'_id': ObjectId(current_user_id)},
                projection={
                    'is_active': 1,
                    'account_id': 1,
                    'whatsapp_business_details': 1
                }
            )
            
            if not user:
                return JsonResponse({
                    'message': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Check subscription status
            subscription = db.find_document(
                'subscriptions',
                {
                    'user_email': current_user_email,
                    'status': 'active',
                    'has_access': True
                },
                projection={'_id': 1}
            )

            # Check for pending bills and date condition
            today = datetime.now()
            is_after_eighth = today.day >= 8
            print(f"is_after_eighth: {is_after_eighth}")
            
            pending_invoice = db.find_document(
                'invoices',
                {
                    'user_id': current_user_id,
                    'payment_status': 'Pending'
                },
                projection={'_id': 1}
            )

            # Prepare response data
            response_data = {
                'has_active_plan': bool(subscription),
                'pending_bills': bool(pending_invoice) if is_after_eighth else False,
                'waba_active': bool(user.get('whatsapp_business_details', {}).get('verified', False)),
                'is_active': user.get('is_active', True),
                'account_id': user.get('account_id', '')
            }

            return JsonResponse({
                'status': 'success',
                'data': response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
