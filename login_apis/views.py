from rest_framework.views import APIView
from django.http import  JsonResponse
from rest_framework import status
from django.contrib.auth.hashers import make_password, check_password
from drf_yasg import openapi
from bson import ObjectId
from drf_yasg.utils import swagger_auto_schema
from utils.database import MongoDB
from utils.auth import generate_tokens, token_required
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
from rest_framework.permissions import IsAuthenticated

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

            # Create user
            user_data = {
                'email': validated_data['email'],
                'password': make_password(validated_data['password']),
                'base_encoded_password': validated_data['password'],
                'first_name': validated_data['first_name'],
                'last_name': validated_data['last_name'],
                'business_number': validated_data['business_number'],
                'business_id': validated_data.get('business_id', ''),
                'default_credit': 1000,
                'is_email_verified': False  # Set default value for email verification
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
                        'is_email_verified': user_data['is_email_verified'] if "is_email_verified" in user_data else False  # Add is_email_verified key
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
                            'is_email_verified': user.get('is_email_verified', False)  # Add is_email_verified key
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
        
            # Check if OTP is expired (2 minutes validity)
            time_diff = datetime.now(timezone.utc) - otp_record[0]['created_at'].astimezone(timezone.utc)
            if time_diff.total_seconds() > 120:  # 2 minutes
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

