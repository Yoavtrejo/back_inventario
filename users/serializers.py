from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Carrera, UserProfile

User = get_user_model()


class UserProfileInfoMixin(serializers.Serializer):
    """Matrícula y carrera (solo lectura); null si el usuario no tiene perfil."""
    matricula = serializers.SerializerMethodField()
    carrera = serializers.SerializerMethodField()

    def get_matricula(self, user) -> str | None:
        profile = getattr(user, 'profile', None)
        return profile.matricula if profile else None

    def get_carrera(self, user) -> str | None:
        profile = getattr(user, 'profile', None)
        return profile.carrera.nombre if profile and profile.carrera else None


class UserSerializer(UserProfileInfoMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id','username','email','first_name','last_name','is_staff','is_active', 'is_superuser', 'date_joined', 'password','last_login',
                  'matricula', 'carrera')
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


class ProfileSerializer(UserProfileInfoMixin, serializers.ModelSerializer):
    """
    Perfil del usuario autenticado. Solo permite editar nombre, apellidos, email y contraseña;
    username, roles y fechas son de solo lectura.
    """

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active',
                  'is_superuser', 'date_joined', 'last_login', 'password', 'matricula', 'carrera')
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


class CarreraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrera
        fields = ('id', 'nombre')


class RegisterSerializer(serializers.Serializer):
    """
    Registro público de alumnos. El username es la matrícula y la cuenta nunca es staff ni superusuario.
    """
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    matricula = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})
    carrera = serializers.PrimaryKeyRelatedField(queryset=Carrera.objects.all())

    def validate_matricula(self, value):
        value = value.strip()
        if (UserProfile.objects.filter(matricula__iexact=value).exists()
                or User.objects.filter(username__iexact=value).exists()):
            raise serializers.ValidationError('Esta matrícula ya está registrada.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Este email ya está registrado.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Las contraseñas no coinciden.'})
        candidate = User(
            username=attrs['matricula'], email=attrs['email'],
            first_name=attrs['first_name'], last_name=attrs['last_name'],
        )
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=validated_data['matricula'],
                    email=validated_data['email'],
                    password=validated_data['password'],
                    first_name=validated_data['first_name'],
                    last_name=validated_data['last_name'],
                    is_staff=False,
                    is_superuser=False,
                )
                UserProfile.objects.create(
                    user=user, matricula=validated_data['matricula'], carrera=validated_data['carrera'],
                )
        except IntegrityError:
            raise serializers.ValidationError({'matricula': 'Esta matrícula ya está registrada.'})
        return user

    def to_representation(self, instance):
        return ProfileSerializer(instance, context=self.context).data
