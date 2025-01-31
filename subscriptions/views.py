from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime
import calendar
from .models import Subscription, Plan
from .serializers import (
    SubscriptionSerializer, PlanSerializer,
    SubscriptionCancelRequestSerializer, RazorpayOrderRequestSerializer
)
from utils.razorpay_helper import (
    create_razorpay_subscription, cancel_razorpay_subscription,
    get_subscription_invoices, create_razorpay_order
)

# Create your views here.

class SubscriptionCancelView(APIView):
    def post(self, request):
        serializer = SubscriptionCancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            email = request.user.email
            subscription = Subscription.objects.get(
                subscription_id=serializer.validated_data['subscription_id'],
                user_email=email
            )
            
            razorpay_response, error = cancel_razorpay_subscription(
                serializer.validated_data['subscription_id']
            )
            
            if error:
                return Response(
                    {"error": f"Failed to cancel subscription: {error}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            subscription.status = 'cancelled'
            subscription.cancelled_at = timezone.now()
            subscription.save()

            return Response({"message": "Subscription cancelled successfully"})

        except Subscription.DoesNotExist:
            return Response(
                {"error": "Subscription not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to cancel subscription: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CreateOrderView(APIView):
    def post(self, request):
        serializer = RazorpayOrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            email = request.user.email
            order_data, error = create_razorpay_order(
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                receipt=serializer.validated_data['receipt'],
                notes={"email": email, "credit": serializer.validated_data['amount']/100}
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
    def get(self, request):
        try:
            plan_id = request.query_params.get('plan_id')
            if not plan_id:
                return Response(
                    {"error": "plan_id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            email = request.user.email
            subscription = Subscription.objects.filter(user_email=email).first()

            if not subscription:
                total_count = 24
                razorpay_response, error = create_razorpay_subscription(
                    plan_id=plan_id,
                    email=email,
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

                subscription = Subscription.objects.create(
                    user_email=email,
                    subscription_id=razorpay_response.get("id"),
                    plan_id=plan_id,
                    total_count=total_count,
                    status=razorpay_response.get("status"),
                    short_url=razorpay_response.get("short_url"),
                    order_id=order_id
                )

            created_date = subscription.created_at
            current_date = timezone.now()

            if subscription.status == "cancelled":
                last_day = calendar.monthrange(created_date.year, created_date.month)[1]
                access_end_date = datetime(
                    created_date.year,
                    created_date.month,
                    last_day,
                    23, 59, 59,
                    tzinfo=timezone.utc
                )
                subscription.access_valid_till = access_end_date
                subscription.has_access = current_date <= access_end_date
            elif subscription.status == "active":
                subscription.has_access = True
                subscription.access_valid_till = None
            else:
                subscription.has_access = False
                subscription.access_valid_till = None

            subscription.save()
            return Response(SubscriptionSerializer(subscription).data)

        except Exception as e:
            return Response(
                {"error": f"Failed to get subscription: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PlansView(APIView):
    def get(self, request):
        try:
            plans = Plan.objects.all()
            serializer = PlanSerializer(plans, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(
                {"error": f"Failed to fetch plans: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class WebhookView(APIView):
    def post(self, request):
        payload = request.data
        event = payload.get("event")
        subscription_id = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("id")

        if subscription_id:
            subscription = Subscription.objects.filter(subscription_id=subscription_id).first()
            if subscription:
                if event == "subscription.activated":
                    subscription.status = "active"
                elif event == "subscription.deactivated":
                    subscription.status = "inactive"
                elif event == "subscription.pending":
                    subscription.status = "pending"
                elif event == "subscription.charged":
                    subscription.status = "active"
                elif event == "subscription.cancelled":
                    subscription.status = "cancelled"
                elif event == "subscription.completed":
                    subscription.status = "completed"
                elif event == "subscription.expired":
                    subscription.delete()
                    return Response({"status": "success"})

                subscription.save()

        elif event == "payment.captured":
            email = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("email")
            credit_to_add = float(payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("credit", 0))
            
            if email:
                # Update user credit (implement according to your User model)
                pass

        return Response({"status": "success"})
