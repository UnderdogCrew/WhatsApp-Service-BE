import jwt
from datetime import datetime, timedelta
from functools import wraps
from django.conf import settings
from django.http import JsonResponse

def generate_tokens(user_id,user_email):
    access_token = jwt.encode({
        'user_id': str(user_id),
        'user_email':user_email,
        'exp': datetime.utcnow() + timedelta(days=1),
        'type': 'access'
    }, settings.SECRET_KEY, algorithm='HS256')
    
    refresh_token = jwt.encode({
        'user_id': str(user_id),
        'user_email':user_email,
        'exp': datetime.utcnow() + timedelta(days=7),
        'type': 'refresh'
    }, settings.SECRET_KEY, algorithm='HS256')
    
    return access_token, refresh_token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        request = args[1]

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return JsonResponse({
                    'message': 'Invalid token format'
                }, status=401)

        if not token:
            return JsonResponse({
                'message': 'Token is missing'
            }, status=401)

        try:
            data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            if data.get('type') != 'access':
                raise jwt.InvalidTokenError('Invalid token type')
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return JsonResponse({
                'message': 'Token has expired'
            }, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({
                'message': str(e)
            }, status=401)
        return f(*args, current_user_id, **kwargs)
    
    return decorated
