from rest_framework import serializers

# Define the serializer
class VerifyBusinessPhoneNumberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15, required=True)  # Example: Validate phone number
    country_code = serializers.CharField(max_length=5, required=True)  # Example: Validate country code