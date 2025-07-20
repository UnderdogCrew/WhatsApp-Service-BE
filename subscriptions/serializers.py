from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Subscription, Plans

class SubscriptionCancelRequestSerializer(serializers.Serializer):
    subscription_id = serializers.CharField()

class RazorpayOrderRequestSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    currency = serializers.CharField()
    receipt = serializers.CharField()

class PaymentVerificationRequestSerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_order_id = serializers.CharField()
    razorpay_signature = serializers.CharField()

class PaymentVerificationResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.DictField(required=False)

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = '__all__'

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plans
        fields = '__all__' 