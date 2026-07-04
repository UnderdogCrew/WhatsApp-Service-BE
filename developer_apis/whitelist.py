WHITELISTED_ENDPOINTS = {
    '/send/message': ['POST'],
    '/messages': ['POST'],
    '/message/logs': ['GET'],
    '/message_templates': ['GET'],
    '/credits': ['GET'],
    '/profile': ['GET'],
    '/dashboard': ['GET'],
    '/dashboard/data': ['GET'],
    '/user/webhook/details': ['GET', 'POST'],
    '/user/status': ['GET'],
    '/whatsapp-templates/': ['GET', 'POST'],
    '/whatsapp-template-by-id/': ['GET'],
    '/customers': ['GET'],
    '/chat/list': ['GET'],
    '/chat/history': ['GET'],
    '/whatsapp/customers': ['GET', 'POST'],
    '/whatsapp/customers/detail/': ['GET'],
}

ALLOWED_FORWARD_HEADERS = {'authorization', 'content-type'}

MAX_BODY_SIZE_BYTES = 1024 * 1024
MAX_QUERY_PARAM_COUNT = 50
MAX_HEADER_VALUE_LENGTH = 500
