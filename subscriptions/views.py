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
    SubscriptionCancelRequestSerializer, RazorpayOrderRequestSerializer,
    PaymentVerificationRequestSerializer, PaymentVerificationResponseSerializer
)
from utils.razorpay_helper import (
    create_razorpay_subscription, cancel_razorpay_subscription,
    get_subscription_invoices, create_razorpay_order,
    verify_razorpay_payment, verify_payment_signature
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

class CreateCreditOrderView(APIView):
    @swagger_auto_schema(
        operation_description="Create a new Razorpay order for credits",
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
        db = MongoDB()
        try:
            order_data, error = create_razorpay_order(
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                receipt=serializer.validated_data['receipt'],
                notes={"email": current_user_email, "user_id": current_user_id, "credits": serializer.validated_data['amount'] / 100}
            )

            db.create_document('payment_orders', {
                "order_id": order_data.get("id"),
                "user_email": current_user_email,
                "user_id": current_user_id,
                "amount": serializer.validated_data['amount'],
                "status": "created",
                "created_at": datetime.now()
            })

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

class PaymentVerificationView(APIView):
    @swagger_auto_schema(
        operation_description="Verify Razorpay payment and update payment order status",
        request_body=PaymentVerificationRequestSerializer,
        responses={
            200: PaymentVerificationResponseSerializer,
            400: 'Bad Request',
            500: 'Internal Server Error'
        }
    )
    def post(self, request):
        """
        Verify Razorpay payment and add credits
        """
        try:
            # Validate request data
            serializer = PaymentVerificationRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Validation error',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            
            # Verify signature
            params_dict = {
                'razorpay_payment_id': validated_data['razorpay_payment_id'],
                'razorpay_order_id': validated_data['razorpay_order_id'],
                'razorpay_signature': validated_data['razorpay_signature']
            }

            if not verify_payment_signature(params_dict):
                return Response({
                    'success': False,
                    'message': 'Payment verification failed'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get payment details
            payment, error = verify_razorpay_payment(
                validated_data['razorpay_payment_id'], 
                validated_data['razorpay_order_id']
            )
            
            if error:
                return Response({
                    'success': False,
                    'message': f'Payment verification failed: {str(error)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if payment['status'] != "captured":
                return Response({
                    'success': False,
                    'message': 'Payment not captured'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get payment order details from MongoDB
            db = MongoDB()
            payment_order = db.find_document(
                'payment_orders',
                {"order_id": validated_data['razorpay_order_id']}
            )

            if not payment_order:
                return Response({
                    'success': False,
                    'message': 'Payment order not found'
                }, status=status.HTTP_404_NOT_FOUND)

            if payment_order.get('status') == 'completed':
                return Response({
                    'success': False,
                    'message': 'Payment already processed'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Calculate credits to add (amount is in paise, so divide by 100)
            amount_in_rupees = payment_order['amount'] / 100
            credits_to_add = amount_in_rupees  # 1 rupee = 1 credit

            # Update payment status
            result = db.update_document(
                'payment_orders',
                {"order_id": validated_data['razorpay_order_id']},
                {
                    "status": "completed",
                    "payment_id": validated_data['razorpay_payment_id'],
                    "completed_at": datetime.now(),
                    "credits_added": credits_to_add
                }
            )

            if result.modified_count == 0:
                return Response({
                    'success': False,
                    'message': 'Failed to update payment order'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Get current user details
            user = db.find_document(
                'users',
                {"_id": ObjectId(payment_order['user_id'])}
            )

            if not user:
                return Response({
                    'success': False,
                    'message': 'User not found'
                }, status=status.HTTP_404_NOT_FOUND)

            # Update user credits
            current_credits = user.get('default_credit', 0)
            new_credits = current_credits + credits_to_add

            credit_update_result = db.update_document(
                'users',
                {"_id": ObjectId(payment_order['user_id'])},
                {"default_credit": new_credits}
            )

            if credit_update_result.modified_count == 0:
                return Response({
                    'success': False,
                    'message': 'Failed to update user credits'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({
                'success': True,
                'message': 'Payment verified successfully and credits added',
                'data': {
                    'credits_added': credits_to_add,
                    'new_credit_balance': new_credits,
                    'amount_paid': amount_in_rupees
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Payment verification failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            has_access = False
            status_update = ""
            print(payload)
            print(event)
            subscription_id = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("id")

            if subscription_id:
                subscription = db.find_document('subscriptions', {'subscription_id': subscription_id})
                if subscription:
                    subscription = convert_object_id(subscription)
                    if event == "subscription.activated":
                        status_update = "active"
                        has_access = True
                    elif event == "subscription.deactivated":
                        status_update = "inactive"
                        has_access = False
                    elif event == "subscription.pending":
                        status_update = "pending"
                        has_access = False
                    elif event == "subscription.charged":
                        status_update = "active"
                        has_access = True
                    elif event == "subscription.cancelled":
                        status_update = "cancelled"
                        has_access = False
                    elif event == "subscription.completed":
                        status_update = "completed"
                        has_access = True
                    elif event == "subscription.expired":
                        db.delete_document('subscriptions', {'subscription_id': subscription_id})
                        return Response({"status": "success"})

                    db.update_document('subscriptions',
                        {'subscription_id': subscription_id},
                        {
                            'status': status_update,
                            'updated_at': datetime.now(timezone.utc),
                            'has_access': has_access
                        }
                    )
                    print(subscription)
                else:
                    print("Subscription not found for subscription id ", subscription_id)
            return Response({"status": "success"})
        except Exception as e:
            return Response(
                {"error": f"Failed to process webhook: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

