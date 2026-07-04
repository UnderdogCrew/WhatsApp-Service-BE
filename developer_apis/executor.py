import json
import time
from urllib.parse import urlencode

from django.test import Client

from developer_apis.whitelist import (
    ALLOWED_FORWARD_HEADERS,
    MAX_BODY_SIZE_BYTES,
    MAX_HEADER_VALUE_LENGTH,
    MAX_QUERY_PARAM_COUNT,
)


def _sanitize_headers(headers):
    if not isinstance(headers, dict):
        return {}

    sanitized = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.lower() not in ALLOWED_FORWARD_HEADERS:
            continue
        sanitized[key] = value[:MAX_HEADER_VALUE_LENGTH]
    return sanitized


def _sanitize_query_params(query_params):
    if not isinstance(query_params, dict):
        return {}

    if len(query_params) > MAX_QUERY_PARAM_COUNT:
        raise ValueError('Too many query parameters')

    sanitized = {}
    for key, value in query_params.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
        elif isinstance(value, list):
            sanitized[key] = [
                item for item in value
                if isinstance(item, (str, int, float, bool)) or item is None
            ]
    return sanitized


def _sanitize_body(body):
    if body is None:
        return None
    if not isinstance(body, dict):
        raise ValueError('Request body must be a JSON object')

    encoded = json.dumps(body)
    if len(encoded) > MAX_BODY_SIZE_BYTES:
        raise ValueError('Request body is too large')

    return body


def _build_http_headers(headers):
    http_headers = {}
    for key, value in headers.items():
        header_name = f'HTTP_{key.upper().replace("-", "_")}'
        http_headers[header_name] = value
    return http_headers


def _parse_response_content(response):
    content_type = response.get('Content-Type', '')
    if 'application/json' in content_type:
        try:
            return response.json()
        except ValueError:
            pass
    return response.content.decode('utf-8', errors='replace')


def execute_whitelisted_request(method, endpoint, headers=None, query_params=None, body=None):
    sanitized_headers = _sanitize_headers(headers or {})
    sanitized_query_params = _sanitize_query_params(query_params or {})
    sanitized_body = _sanitize_body(body)
    http_headers = _build_http_headers(sanitized_headers)
    content_type = sanitized_headers.get('Content-Type', 'application/json')

    client = Client()
    start_time = time.time()
    method = method.upper()
    request_path = endpoint

    if sanitized_query_params:
        query_string = urlencode(sanitized_query_params, doseq=True)
        separator = '&' if '?' in request_path else '?'
        request_path = f'{request_path}{separator}{query_string}'

    if method == 'GET':
        response = client.get(request_path, **http_headers)
    elif method == 'POST':
        response = client.post(
            request_path,
            data=json.dumps(sanitized_body) if sanitized_body is not None else '',
            content_type=content_type,
            **http_headers,
        )
    elif method == 'PUT':
        response = client.put(
            request_path,
            data=json.dumps(sanitized_body) if sanitized_body is not None else '',
            content_type=content_type,
            **http_headers,
        )
    elif method == 'PATCH':
        response = client.patch(
            request_path,
            data=json.dumps(sanitized_body) if sanitized_body is not None else '',
            content_type=content_type,
            **http_headers,
        )
    elif method == 'DELETE':
        response = client.delete(request_path, **http_headers)
    else:
        raise ValueError(f'Unsupported HTTP method: {method}')

    response_time_ms = int((time.time() - start_time) * 1000)
    response_data = _parse_response_content(response)

    return {
        'status_code': response.status_code,
        'response_time_ms': response_time_ms,
        'data': response_data,
    }
