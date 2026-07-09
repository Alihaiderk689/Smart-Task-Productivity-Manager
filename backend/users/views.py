from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import UserSerializer


def hello(request):
    return JsonResponse({
        "message": "Hello from Django!"
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request):

    # Check if email already exists
    if User.objects.filter(email=request.data.get("email")).exists():
        return Response(
            {"message": "Email already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = UserSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.save()

        # create JWT tokens for the new user
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Account created successfully!",
                "user": {"id": user.id, "first_name": user.first_name, "email": user.email},
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    # authenticate using email as username (we set username=email on signup)
    user = authenticate(request, username=email, password=password)

    if user is None:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "user": {"id": user.id, "first_name": user.first_name, "email": user.email},
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profile(request):
    # Protected endpoint: requires JWT in Authorization header
    if not request.user or not request.user.is_authenticated:
        return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

    user = request.user
    return Response({"id": user.id, "first_name": user.first_name, "email": user.email})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """Blacklist the provided refresh token so it can no longer be used."""
    token = request.data.get("refresh")
    if not token:
        return Response({"detail": "Refresh token required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        RefreshToken(token).blacklist()
    except Exception as e:
        return Response({"detail": "Invalid token or token already blacklisted."}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)