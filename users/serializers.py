from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id','username','email','first_name','last_name','is_staff','is_active', 'is_superuser', 'date_joined', 'password','last_login')
        extra_kwargs = {
                            'password': {'write_only': True, 'required': False},
                            'date_joined': {'read_only': True},
                            'last_login': {'read_only': True}
                        }
        
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user
    
    def update(self, instance, validated_data):
        if 'password' in validated_data:
            instance.set_password(validated_data.pop('password'))
        return super().update(instance, validated_data)