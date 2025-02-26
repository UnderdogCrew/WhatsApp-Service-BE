from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime
import calendar
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from utils.database import MongoDB
from .serializers import (
    SubscriptionSerializer, PlanSerializer,
    SubscriptionCancelRequestSerializer, RazorpayOrderRequestSerializer
)
from utils.razorpay_helper import (
    create_razorpay_subscription, cancel_razorpay_subscription,
    get_subscription_invoices, create_razorpay_order
)
from bson import ObjectId
from utils.auth import token_required
import hmac
import hashlib
from UnderdogCrew import settings

def convert_object_id(data):
    """Convert ObjectId to string in MongoDB response"""
    if isinstance(data, list):
        return [convert_object_id(item) for item in data]
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, ObjectId):
                data[key] = str(value)
            elif isinstance(value, (dict, list)):
                data[key] = convert_object_id(value)
        return data 
    return data

# Create your views here.

class SubscriptionCancelView(APIView):
    @swagger_auto_schema(
        operation_description="Cancel an existing subscription",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=SubscriptionCancelRequestSerializer,
        responses={
            200: openapi.Response('Subscription cancelled successfully', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING)
                }
            )),
            404: 'Subscription not found',
            500: 'Internal server error'
        }
    )
    @token_required
    def post(self, request, current_user_id, current_user_email):
        serializer = SubscriptionCancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            db = MongoDB()
            subscription = db.find_document('subscriptions', {
                'subscription_id': serializer.validated_data['subscription_id'],
                'user_email': current_user_email
            })
            
            if not subscription:
                return Response(
                    {"error": "Subscription not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            razorpay_response, error = cancel_razorpay_subscription(
                serializer.validated_data['subscription_id']
            )
            
            if error:
                return Response(
                    {"error": f"Failed to cancel subscription: {error}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            db.update_document('subscriptions', 
                {'subscription_id': serializer.validated_data['subscription_id']},
                {
                    'status': 'cancelled',
                    'cancelled_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
            )

            return Response({"message": "Subscription cancelled successfully"})

        except Exception as e:
            return Response(
                {"error": f"Failed to cancel subscription: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CreateOrderView(APIView):
    @swagger_auto_schema(
        operation_description="Create a new Razorpay order",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=RazorpayOrderRequestSerializer,
        responses={
            200: openapi.Response('Order created successfully', schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'order_id': openapi.Schema(type=openapi.TYPE_STRING)
                }
            )),
            500: 'Internal server error'
        }
    )
    @token_required
    def post(self, request, current_user_id, current_user_email):
        serializer = RazorpayOrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            order_data, error = create_razorpay_order(
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                receipt=serializer.validated_data['receipt'],
                notes={"email": current_user_email, "user_id": current_user_id, "invoice_id": serializer.validated_data['receipt']}
            )

            if error:
                return Response(
                    {"error": f"Failed to create order: {error}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response({
                "message": "Order created successfully",
                "order_id": order_data.get("id"),
            })

        except Exception as e:
            return Response(
                {"error": f"Failed to create order: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SubscriptionView(APIView):
    @swagger_auto_schema(
        operation_description="Get or create a subscription for the authenticated user",
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer token",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'plan_id',
                openapi.IN_QUERY,
                description="ID of the subscription plan",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: SubscriptionSerializer,
            400: 'Plan ID is required',
            500: 'Internal server error'
        }
    )
    @token_required
    def get(self, request, current_user_id, current_user_email):
        try:
            db = MongoDB()
            plan_id = request.query_params.get('plan_id')
            if not plan_id:
                return Response(
                    {"error": "plan_id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            subscription = db.find_document('subscriptions', {'user_email': current_user_email})

            if not subscription:
                total_count = 24
                razorpay_response, error = create_razorpay_subscription(
                    plan_id=plan_id,
                    email=current_user_email,
                    total_count=total_count,
                )

                if error:
                    return Response(
                        {"error": f"Failed to create subscription: {error}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

                order_id = ""
                invoices, error = get_subscription_invoices(razorpay_response.get("id"))
                if not error and invoices:
                    order_id = invoices["items"][0]["order_id"]

                subscription_data = {
                    "user_email": current_user_email,
                    "subscription_id": razorpay_response.get("id"),
                    "plan_id": plan_id,
                    "total_count": total_count,
                    "status": razorpay_response.get("status"),
                    "short_url": razorpay_response.get("short_url"),
                    "order_id": order_id,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
                
                db.create_document('subscriptions', subscription_data)
                subscription = db.find_document('subscriptions', {'user_email': current_user_email})

            created_date = subscription['created_at']
            current_date = datetime.now(timezone.utc)

            if subscription['status'] == "cancelled":
                last_day = calendar.monthrange(created_date.year, created_date.month)[1]
                access_end_date = datetime(
                    created_date.year,
                    created_date.month,
                    last_day,
                    23, 59, 59,
                    tzinfo=timezone.utc
                )
                subscription['access_valid_till'] = access_end_date
                subscription['has_access'] = current_date <= access_end_date
            elif subscription['status'] == "active":
                subscription['has_access'] = True
                subscription['access_valid_till'] = None
            else:
                subscription['has_access'] = False
                subscription['access_valid_till'] = None

            db.update_document('subscriptions', 
                {'_id': subscription['_id']},
                {
                    'has_access': subscription['has_access'],
                    'access_valid_till': subscription['access_valid_till'],
                    'updated_at': datetime.now(timezone.utc)
                }
            )

            # Convert ObjectId to string before returning
            subscription = convert_object_id(subscription)
            return Response(subscription)

        except Exception as e:
            return Response(
                {"error": f"Failed to get subscription: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PlansView(APIView):
    @swagger_auto_schema(
        operation_description="Get all available subscription plans",
        responses={
            200: PlanSerializer(many=True),
            500: 'Internal server error'
        }
    )
    def get(self, request):
        try:
            db = MongoDB()
            plans = db.find_documents('plans', {})
            # Convert ObjectIds to strings
            plans = convert_object_id(plans)
            return Response({"plans": plans})
        except Exception as e:
            return Response(
                {"error": f"Failed to fetch plans: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class WebhookView(APIView):
    def post(self, request):
        try:
            # Get the webhook signature from headers
            webhook_signature = request.headers.get('X-Razorpay-Signature')
            if not webhook_signature:
                return Response(
                    {"error": "Webhook signature is missing"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Get the raw request body
            webhook_body = request.body.decode('utf-8')

            # Verify webhook signature
            expected_signature = hmac.new(
                settings.RAZORPAY_WEBHOOK_SECRET.encode(),
                webhook_body.encode(),
                hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(webhook_signature, expected_signature):
                return Response(
                    {"error": "Invalid webhook signature"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            db = MongoDB()
            payload = request.data
            event = payload.get("event")
            print(event)
            subscription_id = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("id")

            if subscription_id:
                subscription = db.find_document('subscriptions', {'subscription_id': subscription_id})
                if subscription:
                    subscription = convert_object_id(subscription)
                    if event == "subscription.activated":
                        status_update = "active"
                    elif event == "subscription.deactivated":
                        status_update = "inactive"
                    elif event == "subscription.pending":
                        status_update = "pending"
                    elif event == "subscription.charged":
                        status_update = "active"
                    elif event == "subscription.cancelled":
                        status_update = "cancelled"
                    elif event == "subscription.completed":
                        status_update = "completed"
                    elif event == "subscription.expired":
                        db.delete_document('subscriptions', {'subscription_id': subscription_id})
                        return Response({"status": "success"})

                    db.update_document('subscriptions',
                        {'subscription_id': subscription_id},
                        {
                            'status': status_update,
                            'updated_at': datetime.now(timezone.utc),
                            'has_access': status_update == "active"
                        }
                    )

            elif event == "payment.captured":
                email = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("email")
                invoice_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("invoice_id")
                if email:
                    db.update_document('invoices',
                        {'invoice_number': invoice_id},
                        {'$set': {'payment_status': 'Paid', 'updated_at': datetime.now(timezone.utc)}}
                    )

            return Response({"status": "success"})
            
        except Exception as e:
            return Response(
                {"error": f"Failed to process webhook: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
