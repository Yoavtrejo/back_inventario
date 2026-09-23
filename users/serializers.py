from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

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


class ProfileSerializer(serializers.ModelSerializer):
    """
    Perfil del usuario autenticado. Solo permite editar nombre, apellidos, email y contraseña;
    username, roles y fechas son de solo lectura.
    """

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active',
                  'is_superuser', 'date_joined', 'last_login', 'password')
        read_only_fields = ('id', 'username', 'is_staff', 'is_active', 'is_superuser',
                            'date_joined', 'last_login')
        extra_kwargs = {'password': {'write_only': True, 'required': False}}

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError('Este email ya está registrado.')
        return value

    def validate_password(self, value):
        validate_password(value, user=self.instance)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)
