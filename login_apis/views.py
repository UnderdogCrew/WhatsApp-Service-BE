import re
from django.shortcuts import render
from rest_framework.views import APIView
from django.http import HttpResponse, JsonResponse
from rest_framework import status
from django.contrib.auth.hashers import make_password, check_password
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from utils.database import MongoDB
from utils.auth import generate_tokens, token_required
from .serializers import SignupSerializer, LoginSerializer, FileUploadSerializer
from utils.s3_helper import S3Helper

# Create your views here.

class SignupView(APIView):
    @swagger_auto_schema(
        operation_description="Register a new user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='User email'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='User password'),
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username'),
                'business_number': openapi.Schema(type=openapi.TYPE_STRING, description='Business number'),
            },
            required=['email', 'password', 'username', 'business_number']
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

            # Check if user already exists
            if db.find_document('users', {'email': validated_data['email']}):
                return JsonResponse({
                    'message': 'Email already exists'
                }, safe=False, status=status.HTTP_409_CONFLICT)

            # Create user
            user_data = {
                'email': validated_data['email'],
                'password': make_password(validated_data['password']),
                'base_encoded_password': validated_data['password'],
                'username': validated_data['username'],
                'business_number': validated_data['business_number'],
                'default_credit':1000
            }

            user_id = db.create_document('users',user_data)
            access_token, refresh_token = generate_tokens(user_id,validated_data['email'])

            return JsonResponse({
                'status': 'success',
                'message': 'User created successfully',
                'data': {
                    'user': {
                        'id': user_id,
                        'email': validated_data['email'],
                        'username': validated_data['username']
                    },
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    }
                }
            },safe=False, status=status.HTTP_201_CREATED)
        except Exception as e:
            return JsonResponse({
                'message': str(e)
            },safe=False, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    @swagger_auto_schema(
        operation_description="Upload file to S3 bucket",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'file': openapi.Schema(type=openapi.TYPE_FILE, description='File to upload'),
                'file_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Type of file',
                    enum=['image', 'excel', 'doc', 'pdf']
                ),
            },
            required=['file', 'file_type']
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
                            'file_url': openapi.Schema(type=openapi.TYPE_STRING),
                            'file_type': openapi.Schema(type=openapi.TYPE_STRING),
                            'uploaded_by': openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    ),
                }
            )),
            400: 'Bad Request',
            401: 'Unauthorized',
            500: 'Internal Server Error'
        }
    )
    @token_required
    def post(self, request, current_user_id):
        try:
            # Initialize MongoDB connection
            db = MongoDB()
            
            # Validate request data
            serializer = FileUploadSerializer(data=request.data)
            if not serializer.is_valid():
                return JsonResponse({
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            file_obj = validated_data['file']
            file_type = validated_data['file_type']

            # Get user details
            user = db.find_document('users', {'_id': current_user_id})
            if not user:
                return JsonResponse({
                    'message': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Initialize S3 helper and upload file
            s3_helper = S3Helper()
            file_url = s3_helper.upload_file(file_obj, file_type)

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
                    'uploaded_by': user['email'],
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return JsonResponse({
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

