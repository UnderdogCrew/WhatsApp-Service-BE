from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import make_password, check_password
import re
from .database import MongoDB
from .auth import generate_tokens, token_required

# Create your views here.

class SignupView(APIView):
    def post(self, request):
        try:
            data = request.data
            email = data.get('email')
            password = data.get('password')
            username = data.get('username')
            phone_number = data.get('phone_number')

            # Validate email format
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                return Response({
                    'status': 'error',
                    'message': 'Invalid email format'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Initialize MongoDB connection
            db = MongoDB()

            # Check if user already exists
            if db.find_user_by_email(email):
                return Response({
                    'status': 'error',
                    'message': 'Email already exists'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Create user
            user_data = {
                'email': email,
                'password': make_password(password),
                'username': username,
                'phone_number': phone_number
            }

            user_id = db.create_user(user_data)
            access_token, refresh_token = generate_tokens(user_id)

            return Response({
                'status': 'success',
                'message': 'User created successfully',
                'data': {
                    'user': {
                        'id': user_id,
                        'email': email,
                        'username': username
                    },
                    'tokens': {
                        'access': access_token,
                        'refresh': refresh_token
                    }
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(APIView):
    def post(self, request):
        try:
            data = request.data
            email = data.get('email')
            password = data.get('password')

            db = MongoDB()
            user = db.find_user_by_email(email)

            if user and check_password(password, user['password']):
                access_token, refresh_token = generate_tokens(user['_id'])
                
                return Response({
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
                })
            
            return Response({
                'status': 'error',
                'message': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProtectedView(APIView):
    @token_required
    def get(self, request, current_user_id):
        try:
            db = MongoDB()
            user = db.find_user_by_id(current_user_id)
            
            return Response({
                'status': 'success',
                'message': 'Protected data retrieved',
                'data': {
                    'user': {
                        'id': str(user['_id']),
                        'email': user['email'],
                        'username': user['username']
                    }
                }
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
