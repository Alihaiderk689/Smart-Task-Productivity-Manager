from __future__ import annotations

from rest_framework import serializers


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(allow_blank=True, trim_whitespace=False)


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=2000)
    # Client-held conversation history, resent every request -- see
    # services/chat_service.py's module docstring for why nothing is
    # persisted server-side.
    history = ChatMessageSerializer(many=True, required=False, default=list)
