import jwt
from datetime import datetime, timedelta
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from forex_python.converter import CurrencyRates


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
            current_user_email = data['user_email']
        except jwt.ExpiredSignatureError:
            return JsonResponse({
                'message': 'Token has expired'
            }, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({
                'message': str(e)
            }, status=401)
        return f(*args, current_user_id, current_user_email, **kwargs)
    
    return decorated

def decode_token(token):
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return data
    except jwt.ExpiredSignatureError:
        return {'message': 'Token has expired'}
    except jwt.InvalidTokenError as e:
        return {'message': str(e)}


def current_dollar_price():
    # Create an instance of CurrencyRates
    c = CurrencyRates()

    # Get the current USD to INR rate
    usd_to_inr_rate = c.get_rate('USD', 'INR')

    print(f"The current USD to INR exchange rate is: {usd_to_inr_rate}")
    return usd_to_inr_rate