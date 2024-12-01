from rest_framework import serializers
import re
from django.core.validators import FileExtensionValidator

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
    file = serializers.FileField(
        validators=[FileExtensionValidator(
            allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx']
        )]
    )
    file_type = serializers.ChoiceField(
        choices=['image', 'document', 'excel'],
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