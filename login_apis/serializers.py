from rest_framework import serializers
import re

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=50)
    username = serializers.CharField(min_length=3, max_length=50)
    business_number = serializers.CharField(max_length=20)

    def validate_password(self, value):
        # Password validation: min 8 chars, must include letter, number, and special char
        if not re.match(r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$', value):
            raise serializers.ValidationError(
                "Password must be at least 8 characters long and contain at least one letter, "
                "one number, and one special character (@$!%*#?&)"
            )
        return value

    def validate_business_number(self, value):
        # Custom business number validation
        if not value.isalnum():
            raise serializers.ValidationError(
                "Business number must contain only letters and numbers"
            )
        return value

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField() 

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    file_type = serializers.ChoiceField(choices=['image', 'excel', 'doc', 'pdf'])