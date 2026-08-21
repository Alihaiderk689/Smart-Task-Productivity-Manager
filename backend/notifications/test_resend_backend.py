import pytest
from django.core.mail import EmailMultiAlternatives
from resend.exceptions import ApplicationError

from notifications.resend_backend import ResendEmailBackend


def _message(**overrides):
    kwargs = dict(
        subject="Hello",
        body="plain text body",
        from_email="sender@example.com",
        to=["recipient@example.com"],
    )
    kwargs.update(overrides)
    return EmailMultiAlternatives(**kwargs)


def test_send_messages_returns_zero_for_empty_list():
    assert ResendEmailBackend().send_messages([]) == 0


def test_sets_api_key_from_settings_and_sends_via_resend(settings, monkeypatch):
    settings.RESEND_API_KEY = "re_test_key"
    captured = {}

    def fake_send(params):
        captured.update(params)
        return {"id": "abc123"}

    monkeypatch.setattr("notifications.resend_backend.resend.Emails.send", fake_send)

    message = _message()
    message.attach_alternative("<p>hi</p>", "text/html")

    sent = ResendEmailBackend().send_messages([message])

    import resend
    assert resend.api_key == "re_test_key"
    assert sent == 1
    assert captured["from"] == "sender@example.com"
    assert captured["to"] == ["recipient@example.com"]
    assert captured["subject"] == "Hello"
    assert captured["text"] == "plain text body"
    assert captured["html"] == "<p>hi</p>"


def test_omits_html_when_no_alternative_attached(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "notifications.resend_backend.resend.Emails.send",
        lambda params: captured.update(params) or {"id": "x"},
    )

    ResendEmailBackend().send_messages([_message()])

    assert "html" not in captured


def test_includes_cc_bcc_reply_to_when_present(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "notifications.resend_backend.resend.Emails.send",
        lambda params: captured.update(params) or {"id": "x"},
    )

    message = _message(cc=["cc@example.com"], bcc=["bcc@example.com"], reply_to=["reply@example.com"])
    ResendEmailBackend().send_messages([message])

    assert captured["cc"] == ["cc@example.com"]
    assert captured["bcc"] == ["bcc@example.com"]
    assert captured["reply_to"] == ["reply@example.com"]


def test_raises_when_fail_silently_is_false(monkeypatch):
    def boom(params):
        raise ApplicationError(message="down", error_type="application_error", code=500)

    monkeypatch.setattr("notifications.resend_backend.resend.Emails.send", boom)

    backend = ResendEmailBackend(fail_silently=False)
    with pytest.raises(ApplicationError):
        backend.send_messages([_message()])


def test_swallows_failure_when_fail_silently_is_true(monkeypatch):
    def boom(params):
        raise ApplicationError(message="down", error_type="application_error", code=500)

    monkeypatch.setattr("notifications.resend_backend.resend.Emails.send", boom)

    backend = ResendEmailBackend(fail_silently=True)
    sent = backend.send_messages([_message()])

    assert sent == 0


def test_one_failure_does_not_stop_the_rest_of_the_batch(monkeypatch):
    calls = []

    def flaky(params):
        calls.append(params["to"])
        if params["to"] == ["fails@example.com"]:
            raise ApplicationError(message="down", error_type="application_error", code=500)
        return {"id": "ok"}

    monkeypatch.setattr("notifications.resend_backend.resend.Emails.send", flaky)

    backend = ResendEmailBackend(fail_silently=True)
    sent = backend.send_messages([
        _message(to=["fails@example.com"]),
        _message(to=["ok@example.com"]),
    ])

    assert sent == 1
    assert len(calls) == 2
