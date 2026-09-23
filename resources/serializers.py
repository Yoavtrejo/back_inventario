from rest_framework import serializers

from .models import Resource


class ResourceSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Resource
        fields = ('id', 'title', 'description', 'file', 'created_by', 'created_by_name', 'created_at')
        read_only_fields = ('id', 'created_by', 'created_at')

    def get_created_by_name(self, obj) -> str:
        return obj.created_by.get_full_name() or obj.created_by.username
