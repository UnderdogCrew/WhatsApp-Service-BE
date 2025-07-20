from rest_framework import serializers

# Define the serializer
class VerifyBusinessPhoneNumberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15, required=True)  # Example: Validate phone number
    country_code = serializers.CharField(max_length=5, required=True)  # Example: Validate country code


class ButtonSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['QUICK_REPLY','COPY_CODE','PHONE_NUMBER','URL'], required=True)
    text = serializers.CharField(required=True)
    phone_number = serializers.CharField(required=False)
    url = serializers.CharField(required=False)
    copy_code = serializers.CharField(required=False)
    example = serializers.CharField(required=False)

class ComponentSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=['HEADER', 'BODY', 'FOOTER', 'BUTTONS'],
        required=True
    )
    format = serializers.ChoiceField(
        choices=['TEXT', 'IMAGE', 'VIDEO', 'DOCUMENT', 'LOCATION'],
        required=False
    )
    text = serializers.CharField(required=False)
    buttons = ButtonSerializer(many=True, required=False)
    example = serializers.DictField(required=False)

    def validate(self, data):
        component_type = data.get('type')
        
        if component_type == 'BODY' and 'text' not in data:
            raise serializers.ValidationError("BODY component must have text field")
        
        if component_type == 'HEADER':
            if 'format' not in data:
                raise serializers.ValidationError("HEADER component must have format field")
            if data['format'] == 'TEXT' and 'text' not in data:
                raise serializers.ValidationError("HEADER component with TEXT format must have text field")
        
        if component_type == 'FOOTER' and 'text' not in data:
            raise serializers.ValidationError("FOOTER component must have text field")
        
        if component_type == 'BUTTONS' and 'buttons' not in data:
            raise serializers.ValidationError("BUTTONS component must have buttons array")
            
        return data

class WhatsAppTemplateSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    language = serializers.CharField(required=True)
    category = serializers.ChoiceField(
        choices=['MARKETING', 'UTILITY'],
        required=True
    )
    components = ComponentSerializer(many=True, required=True)

class WhatsAppTemplateEditSerializer(serializers.Serializer):
    category = serializers.ChoiceField(
        choices=['MARKETING', 'UTILITY'],
        required=False
    )
    components = ComponentSerializer(many=True, required=False)
    
    def validate(self, data):
        # At least one field must be provided
        if not data.get('category') and not data.get('components'):
            raise serializers.ValidationError("Either category or components must be provided")
        return data 