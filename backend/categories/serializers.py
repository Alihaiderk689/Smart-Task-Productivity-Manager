from rest_framework import serializers
from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        name = attrs.get("name")
        if not name:
            return attrs
        
        request = self.context.get("request")
        if not request:
            return attrs
            
        user = request.user
        queryset = Category.objects.filter(user=user, name__iexact=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError({"name": "Category with this name already exists for this user."})
        return attrs