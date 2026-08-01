import pytest
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from .exception_handler import custom_exception_handler


def test_unhandled_exception_returns_generic_500():
    response = custom_exception_handler(ValueError("boom"), {"request": None, "view": None})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data == {"detail": "An unexpected error occurred. Please try again."}


def test_known_drf_exception_is_left_to_the_default_handler():
    # NotFound is a case DRF's default handler already formats correctly --
    # our handler should pass it straight through unchanged, not override it.
    response = custom_exception_handler(NotFound("nope"), {"request": None, "view": None})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data == {"detail": "nope"}


class _BrokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raise ValueError("something broke")


@pytest.mark.django_db
def test_broken_view_returns_json_not_a_traceback_page():
    request = APIRequestFactory().get("/broken/")
    response = _BrokenView.as_view()(request)

    assert response.status_code == 500
    assert response.data == {"detail": "An unexpected error occurred. Please try again."}
