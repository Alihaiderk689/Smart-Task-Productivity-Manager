import pytest
import requests
from django.core.mail import EmailMultiAlternatives

from notifications.brevo_backend import BrevoAPIError, BrevoEmailBackend


def _message(**overrides):
    kwargs = dict(
        subject="Hello",
        body="plain text body",
        from_email="sender@example.com",
        to=["recipient@example.com"],
    )
    kwargs.update(overrides)
    return EmailMultiAlternatives(**kwargs)


class _FakeResponse:
    def __init__(self, status_code=201, text='{"messageId": "abc123"}'):
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 300


def test_send_messages_returns_zero_for_empty_list():
    assert BrevoEmailBackend().send_messages([]) == 0


def test_sends_correct_payload_and_headers(settings, monkeypatch):
    settings.BREVO_API_KEY = "brevo_test_key"
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("notifications.brevo_backend.requests.post", fake_post)

    message = _message()
    message.attach_alternative("<p>hi</p>", "text/html")

    sent = BrevoEmailBackend().send_messages([message])

    assert sent == 1
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["api-key"] == "brevo_test_key"
    assert captured["json"]["sender"] == {"email": "sender@example.com"}
    assert captured["json"]["to"] == [{"email": "recipient@example.com"}]
    assert captured["json"]["subject"] == "Hello"
    assert captured["json"]["textContent"] == "plain text body"
    assert captured["json"]["htmlContent"] == "<p>hi</p>"


def test_omits_html_content_when_no_alternative_attached(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "notifications.brevo_backend.requests.post",
        lambda url, json, headers, timeout: captured.update(json) or _FakeResponse(),
    )

    BrevoEmailBackend().send_messages([_message()])

    assert "htmlContent" not in captured


def test_includes_cc_bcc_reply_to_when_present(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "notifications.brevo_backend.requests.post",
        lambda url, json, headers, timeout: captured.update(json) or _FakeResponse(),
    )

    message = _message(cc=["cc@example.com"], bcc=["bcc@example.com"], reply_to=["reply@example.com"])
    BrevoEmailBackend().send_messages([message])

    assert captured["cc"] == [{"email": "cc@example.com"}]
    assert captured["bcc"] == [{"email": "bcc@example.com"}]
    assert captured["replyTo"] == {"email": "reply@example.com"}


def test_parses_display_name_from_from_email(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "notifications.brevo_backend.requests.post",
        lambda url, json, headers, timeout: captured.update(json) or _FakeResponse(),
    )

    message = _message(from_email="Smart Task Manager <sender@example.com>")
    BrevoEmailBackend().send_messages([message])

    assert captured["sender"] == {"email": "sender@example.com", "name": "Smart Task Manager"}


def test_raises_brevo_api_error_on_non_2xx_when_fail_silently_is_false(monkeypatch):
    monkeypatch.setattr(
        "notifications.brevo_backend.requests.post",
        lambda url, json, headers, timeout: _FakeResponse(status_code=401, text='{"message": "invalid api key"}'),
    )

    backend = BrevoEmailBackend(fail_silently=False)
    with pytest.raises(BrevoAPIError):
        backend.send_messages([_message()])


def test_raises_brevo_api_error_on_network_failure(monkeypatch):
    def boom(url, json, headers, timeout):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("notifications.brevo_backend.requests.post", boom)

    backend = BrevoEmailBackend(fail_silently=False)
    with pytest.raises(BrevoAPIError):
        backend.send_messages([_message()])


def test_swallows_failure_when_fail_silently_is_true(monkeypatch):
    monkeypatch.setattr(
        "notifications.brevo_backend.requests.post",
        lambda url, json, headers, timeout: _FakeResponse(status_code=500, text="down"),
    )

    backend = BrevoEmailBackend(fail_silently=True)
    sent = backend.send_messages([_message()])

    assert sent == 0


def test_one_failure_does_not_stop_the_rest_of_the_batch(monkeypatch):
    calls = []

    def flaky(url, json, headers, timeout):
        calls.append(json["to"])
        if json["to"] == [{"email": "fails@example.com"}]:
            return _FakeResponse(status_code=500, text="down")
        return _FakeResponse()

    monkeypatch.setattr("notifications.brevo_backend.requests.post", flaky)

    backend = BrevoEmailBackend(fail_silently=True)
    sent = backend.send_messages([
        _message(to=["fails@example.com"]),
        _message(to=["ok@example.com"]),
    ])

    assert sent == 1
    assert len(calls) == 2
