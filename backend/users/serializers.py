from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers      #This imports Django REST Framework's serializer classes.


class UserSerializer(serializers.ModelSerializer):      #creating a serializer for the user model.
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)   #write_only=true means that the password field will accept the incoming password but not send it back in the response. This is a security measure to prevent exposing the password in API responses.

    class Meta:
        model = User        #This serializer works with the User model.
        fields = ["first_name", "email", "password"] #we only want to expose these.

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],      # username = email
            first_name=validated_data["first_name"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        return user


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
