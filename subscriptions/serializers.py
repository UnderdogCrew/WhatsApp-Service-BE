from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Subscription, Plan

class SubscriptionCancelRequestSerializer(serializers.Serializer):
    subscription_id = serializers.CharField()

class RazorpayOrderRequestSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    currency = serializers.CharField()
    receipt = serializers.CharField()

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = '__all__'

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__' 