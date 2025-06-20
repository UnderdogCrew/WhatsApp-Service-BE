from rest_framework import serializers
import re
from django.core.validators import FileExtensionValidator

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=50)
    first_name = serializers.CharField(max_length=20)
    last_name = serializers.CharField(max_length=20)
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
        # Custom business number (phone number) validation
        if not re.match(r'^\+\d{1,3}\d{10,15}$', value):
            raise serializers.ValidationError(
                "Business number must include country code and be followed by the number"
            )
        return value

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField() 

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(
        validators=[FileExtensionValidator(
            allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', "mp4"]
        )]
    )
    file_type = serializers.ChoiceField(
        choices=['image', 'document', 'excel', "video"],
        required=True
    )


class FileUploadResponseSerializer(serializers.Serializer):
    status = serializers.CharField(default='success')
    message = serializers.CharField(default='File uploaded successfully')
    data = serializers.DictField(
        child=serializers.CharField(),
        default={
            'file_url': serializers.CharField(),
            'file_type': serializers.CharField(),
            'file_name': serializers.CharField(),
            'file_size': serializers.IntegerField(),
            'mime_type': serializers.CharField(),
            'uploaded_by': serializers.CharField()
        }
    )

class BusinessDetailsSerializer(serializers.Serializer):
    category = serializers.CharField(required=False, allow_blank=True, max_length=255)
    business_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    timezone = serializers.CharField(required=False, allow_blank=True, max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, max_length=500)  # Optional field

class CustomerSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=15, required=True)
    name = serializers.CharField(max_length=100, required=True)
    status = serializers.IntegerField(default=1)
    tags = serializers.CharField(max_length=20, required=False, allow_blank=True)
    source = serializers.CharField(max_length=50, required=False, allow_blank=True)

class CustomerUpdateSerializer(serializers.Serializer):
    customer_id = serializers.CharField(max_length=50, required=False)
    number = serializers.CharField(max_length=15, required=False)
    name = serializers.CharField(max_length=100, required=False)
    status = serializers.IntegerField(required=False)
    tags = serializers.CharField(max_length=20, required=False, allow_blank=True)
    source = serializers.CharField(max_length=50, required=False, allow_blank=True)


