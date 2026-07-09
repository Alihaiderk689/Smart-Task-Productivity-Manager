from django.contrib.auth.models import User
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["first_name", "email", "password"]

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],      # username = email
            first_name=validated_data["first_name"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        return user