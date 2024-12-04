from rest_framework.views import APIView
from django.http import  JsonResponse
from rest_framework import status
from django.contrib.auth.hashers import make_password, check_password
from drf_yasg import openapi
from bson import ObjectId
from drf_yasg.utils import swagger_auto_schema
from utils.database import MongoDB
from utils.auth import generate_tokens, token_required
from .serializers import SignupSerializer, LoginSerializer, FileUploadSerializer, FileUploadResponseSerializer
from utils.s3_helper import S3Helper
from .utils import get_file_extension, validate_file
from rest_framework.parsers import MultiPartParser, FormParser
from utils.twilio_otp import generate_otp, send_otp
from datetime import datetime, timezone
import twilio
import re

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
                'default_credit': 1000
            }

            user_id = db.create_document('users', user_data)
            access_token, refresh_token = generate_tokens(user_id, validated_data['email'])

            return JsonResponse({
                'status': 'success',
                'message': 'User created successfully',
                'data': {
                    'user': {
                        'id': user_id,
                        'email': validated_data['email'],
                        'first_name': validated_data['first_name'],
                        'last_name': validated_data['last_name'],
                        'business_id': user_data['business_id']
                    },
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    }
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
                access_token, refresh_token = generate_tokens(str(user['_id']),validated_data['email'])
                return JsonResponse({
                    'status': 'success',
                    'message': 'Login successful',
                    'data': {
                        'user': {
                            'id': str(user['_id']),
                            'email': user['email'],
                            'username': user['username']
                        },
                        'tokens': {
                            'access': access_token,
                            'refresh': refresh_token
                        }
                    }
                },safe=False, status=status.HTTP_200_OK)
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
    def post(self, request, current_user_id):
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
                file_extension=file_extension
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

