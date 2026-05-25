from rest_framework import serializers
from .models import Material

class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate(self, data):
        # Ensure quantity is not negative
        if data.get('quantity', 0) < 0:
            raise serializers.ValidationError("La cantidad no puede ser negativa.")
        return data

    def create(self, validated_data):
        return Material.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.quantity = validated_data.get('quantity', instance.quantity)
        instance.min_stock = validated_data.get('min_stock', instance.min_stock)
        instance.max_stock = validated_data.get('max_stock', instance.max_stock)
        instance.status = validated_data.get('status', instance.status)
        instance.save()
        return instance