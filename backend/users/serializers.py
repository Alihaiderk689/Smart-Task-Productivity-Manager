from django.contrib.auth.models import User
from rest_framework import serializers      #This imports Django REST Framework's serializer classes.

from .validators import normalize_email, validate_full_name, validate_password_complexity


class UserSerializer(serializers.ModelSerializer):      #creating a serializer for the user model.
    # "first_name" is the User model's only name field -- used to hold the
    # full name the signup form collects (see users/validators.py for the
    # actual rules; email templates/profile UI already display it as-is).
    first_name = serializers.CharField(
        required=True,
        error_messages={"required": "Full name is required.", "blank": "Full name is required."},
    )
    email = serializers.EmailField(
        required=True,
        error_messages={
            "required": "Email is required.",
            "blank": "Email is required.",
            "invalid": "Please enter a valid email address.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        error_messages={"required": "Password is required.", "blank": "Password is required."},
    )   #write_only=true means that the password field will accept the incoming password but not send it back in the response. This is a security measure to prevent exposing the password in API responses.
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        error_messages={"required": "Please confirm your password.", "blank": "Please confirm your password."},
    )

    class Meta:
        model = User        #This serializer works with the User model.
        fields = ["first_name", "email", "password", "password_confirm"] #we only want to expose these.

    def validate_first_name(self, value):
        return validate_full_name(value)

    def validate_email(self, value):
        value = normalize_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_password(self, value):
        return validate_password_complexity(value)

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})

        email = attrs.get("email")
        password = attrs.get("password")
        if email and password and password.strip().lower() == email.strip().lower():
            raise serializers.ValidationError({"password": "Password cannot be the same as your email."})

        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],      # username = email
            first_name=validated_data["first_name"],
            email=validated_data["email"],
            password=validated_data["password"],
            is_active=False,  # activated once the emailed verification code is entered
        )
        return user


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return validate_password_complexity(value)


class EmailOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the 6-digit code."})


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    avatar = serializers.ImageField(required=False, allow_null=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return validate_password_complexity(value)
