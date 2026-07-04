import logging

from django.http import JsonResponse
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.views import APIView

from developer_apis.executor import execute_whitelisted_request
from developer_apis.rate_limiter import check_try_now_rate_limit
from developer_apis.whitelist import WHITELISTED_ENDPOINTS
from utils.auth import decode_token, token_required

logger = logging.getLogger(__name__)


def _normalize_endpoint(endpoint):
    if not isinstance(endpoint, str):
        return None, 'endpoint must be a string'

    endpoint = endpoint.strip()
    if not endpoint:
        return None, 'endpoint is required'

    if '://' in endpoint or endpoint.startswith('//'):
        return None, 'External URLs are not allowed'

    if '..' in endpoint or '\x00' in endpoint:
        return None, 'Invalid endpoint path'

    if not endpoint.startswith('/'):
        endpoint = f'/{endpoint}'

    endpoint = endpoint.rstrip('/') if endpoint != '/' else endpoint
    if endpoint in WHITELISTED_ENDPOINTS:
        return endpoint, None

    endpoint_with_slash = f'{endpoint}/'
    if endpoint_with_slash in WHITELISTED_ENDPOINTS:
        return endpoint_with_slash, None

    return None, 'Endpoint is not allowed'


def _build_validation_error(message, status_code=400):
    return JsonResponse({
        'success': False,
        'status_code': status_code,
        'response_time_ms': 0,
        'error': {'message': message},
    }, status=status_code)


def _build_response(success, status_code, response_time_ms, payload):
    response = {
        'success': success,
        'status_code': status_code,
        'response_time_ms': response_time_ms,
    }
    if success:
        response['data'] = payload
    else:
        response['error'] = payload
    return JsonResponse(response, status=status_code)


class TryNowView(APIView):
    @swagger_auto_schema(
        operation_description='Execute a whitelisted WapNexus API endpoint for the Try Now feature',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'method': openapi.Schema(type=openapi.TYPE_STRING, description='HTTP method'),
                'endpoint': openapi.Schema(type=openapi.TYPE_STRING, description='Whitelisted API endpoint path'),
                'headers': openapi.Schema(type=openapi.TYPE_OBJECT, description='Request headers'),
                'query_params': openapi.Schema(type=openapi.TYPE_OBJECT, description='Query parameters'),
                'body': openapi.Schema(type=openapi.TYPE_OBJECT, description='Request body'),
            },
            required=['method', 'endpoint'],
        ),
        responses={
            200: 'Successful proxy response',
            400: 'Validation error',
            401: 'Unauthorized',
            403: 'Forbidden',
            429: 'Rate limit exceeded',
        },
    )
    @token_required
    def post(self, request, current_user_id, current_user_email):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.split(' ')[1] if ' ' in auth_header else None
        token_data = decode_token(token) if token else {}
        if token_data.get('type') != 'access':
            return _build_validation_error(
                'Only logged-in users can use this feature',
                status_code=403,
            )

        if not check_try_now_rate_limit(current_user_id):
            return _build_validation_error(
                'Rate limit exceeded. Please try again later.',
                status_code=429,
            )

        payload = request.data
        if not isinstance(payload, dict):
            return _build_validation_error('Request body must be a JSON object')

        method = payload.get('method')
        endpoint = payload.get('endpoint')
        headers = payload.get('headers', {})
        query_params = payload.get('query_params', {})
        body = payload.get('body')

        if not method or not isinstance(method, str):
            return _build_validation_error('method is required')

        method = method.upper()
        normalized_endpoint, endpoint_error = _normalize_endpoint(endpoint)
        if endpoint_error:
            return _build_validation_error(endpoint_error)

        allowed_methods = WHITELISTED_ENDPOINTS.get(normalized_endpoint, [])
        if method not in allowed_methods:
            return _build_validation_error(
                f'Method {method} is not allowed for endpoint {normalized_endpoint}',
            )

        logger.info(
            'Try now request user_id=%s endpoint=%s method=%s',
            current_user_id,
            normalized_endpoint,
            method,
        )

        try:
            result = execute_whitelisted_request(
                method=method,
                endpoint=normalized_endpoint,
                headers=headers,
                query_params=query_params,
                body=body,
            )
        except ValueError as exc:
            return _build_validation_error(str(exc))
        except Exception:
            logger.exception(
                'Try now execution failed user_id=%s endpoint=%s method=%s',
                current_user_id,
                normalized_endpoint,
                method,
            )
            return _build_validation_error('Failed to execute request', status_code=500)

        status_code = result['status_code']
        response_time_ms = result['response_time_ms']
        response_data = result['data']
        success = 200 <= status_code < 400

        return _build_response(success, status_code, response_time_ms, response_data)
