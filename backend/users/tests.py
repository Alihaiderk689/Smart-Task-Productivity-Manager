from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class SignupViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_rejects_short_passwords(self):
        response = self.client.post(
            "/api/signup/",
            {
                "first_name": "Test",
                "email": "shortpass@example.com",
                "password": "ab",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.json())


class LogoutViewTests(TestCase):
    def setUp(self): 
        self.client = APIClient() #creates your fake postman.
        self.user = User.objects.create_user(       #create_user hashes the password automatically.
            username="logout-user@example.com",
            email="logout-user@example.com",
            password="TestPass123!",
        )

    def test_logout_succeeds_when_refresh_token_is_already_blacklisted(self):
        self.client.force_authenticate(user=self.user)      #authenticate the user for the test client.
        refresh = RefreshToken.for_user(self.user)          #generate refresh token.
        refresh.blacklist()                                 #now the token is invalid.

        response = self.client.post(
            "/api/logout/",
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)         #it expects the api to return 200 status code.
        self.assertEqual(response.json()["detail"], "Logout successful.")       #expect the json for this exact message.
