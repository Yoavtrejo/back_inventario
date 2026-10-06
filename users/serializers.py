from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import Carrera, UserProfile, normalizar_clave

User = get_user_model()



def revoke_refresh_tokens(user):
    """Invalida todos los refresh tokens del usuario (cierra sus sesiones)."""
    for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
        BlacklistedToken.objects.get_or_create(token=token)

class UserProfileInfoMixin(serializers.Serializer):
    """
    Datos del perfil del alumno (solo lectura); null si no tiene perfil o falta el dato.
    Cada serializer elige en Meta.fields cuáles expone.
    """
    matricula = serializers.SerializerMethodField()
    carrera = serializers.SerializerMethodField()
    carrera_id = serializers.SerializerMethodField()
    carrera_clave = serializers.SerializerMethodField()
    cuatrimestre = serializers.SerializerMethodField()
    grupo = serializers.SerializerMethodField()
    grupo_escolar = serializers.SerializerMethodField()

    @staticmethod
    def _profile(user):
        return getattr(user, 'profile', None)

    def get_matricula(self, user) -> str | None:
        profile = self._profile(user)
        return profile.matricula if profile else None

    def get_carrera(self, user) -> str | None:
        profile = self._profile(user)
        return profile.carrera.nombre if profile and profile.carrera else None

    def get_carrera_id(self, user) -> int | None:
        profile = self._profile(user)
        return profile.carrera_id if profile else None

    def get_carrera_clave(self, user) -> str | None:
        profile = self._profile(user)
        return profile.carrera.clave if profile and profile.carrera else None

    def get_cuatrimestre(self, user) -> int | None:
        profile = self._profile(user)
        return profile.cuatrimestre if profile else None

    def get_grupo(self, user) -> int | None:
        profile = self._profile(user)
        return profile.grupo if profile else None

    def get_grupo_escolar(self, user) -> str | None:
        """Ej. 'ISC34'; null si falta la clave de la carrera, el cuatrimestre o el grupo."""
        profile = self._profile(user)
        if profile and profile.carrera and profile.carrera.clave and profile.cuatrimestre and profile.grupo:
            return f"{profile.carrera.clave}{profile.cuatrimestre}{profile.grupo}"
        return None


PROFILE_INFO_FIELDS = ('matricula', 'carrera', 'carrera_id', 'carrera_clave', 'cuatrimestre', 'grupo', 'grupo_escolar')
COHORT_KEYS = ('carrera', 'cuatrimestre', 'grupo')


class CohortInputSerializer(serializers.Serializer):
    """Entrada de carrera (id), cuatrimestre (1-9) y grupo (1-6) del perfil del alumno."""
    carrera = serializers.PrimaryKeyRelatedField(queryset=Carrera.objects.all(), allow_null=True, required=False)
    cuatrimestre = serializers.IntegerField(min_value=1, max_value=9, allow_null=True, required=False)
    grupo = serializers.IntegerField(min_value=1, max_value=6, allow_null=True, required=False)


def validated_cohort_input(initial_data):
    """Valida solo las claves de cohorte presentes en la petición; {} si no viene ninguna."""
    data = {key: initial_data[key] for key in COHORT_KEYS if key in initial_data}
    if not data:
        return {}
    serializer = CohortInputSerializer(data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def save_cohort(user, cohort_data):
    """Guarda la cohorte en el perfil (lo crea si falta). Devuelve (cohorte anterior, cohorte nueva)."""
    profile = getattr(user, 'profile', None)
    if profile is None:
        profile = UserProfile.objects.create(user=user, matricula=user.username)
        user.profile = profile
    old_cohort = profile.cohorte
    for key, value in cohort_data.items():
        setattr(profile, key, value)
    profile.save()
    return old_cohort, profile.cohorte


class UserSerializer(UserProfileInfoMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id','username','email','first_name','last_name','is_staff','is_active', 'is_superuser', 'date_joined', 'password','last_login',
                  *PROFILE_INFO_FIELDS)
        extra_kwargs = {
                            'password': {'write_only': True, 'required': False},
                            'date_joined': {'read_only': True},
                            'last_login': {'read_only': True}
                        }
        
    def validate(self, attrs):
        # El admin puede fijar o cambiar carrera, cuatrimestre y grupo del alumno
        attrs['_cohort'] = validated_cohort_input(self.initial_data)
        return attrs

    def create(self, validated_data):
        cohort_data = validated_data.pop('_cohort', {})
        user = User.objects.create_user(**validated_data)
        if cohort_data:
            save_cohort(user, cohort_data)
            from academic.enrollment import enroll_student
            enroll_student(user)
        return user
    
    def update(self, instance, validated_data):
        cohort_data = validated_data.pop('_cohort', {})
        if 'password' in validated_data:
            instance.set_password(validated_data.pop('password'))
        user = super().update(instance, validated_data)
        if cohort_data:
            old_cohort, new_cohort = save_cohort(user, cohort_data)
            from academic.enrollment import move_student
            move_student(user, old_cohort, new_cohort)
        return user


class ProfileSerializer(UserProfileInfoMixin, serializers.ModelSerializer):
    """
    Perfil del usuario autenticado. Solo permite editar nombre, apellidos, email y contraseña;
    username, roles y fechas son de solo lectura.
    """

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active',
                  'is_superuser', 'date_joined', 'last_login', 'password', *PROFILE_INFO_FIELDS)
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

    COHORT_LOCKED_MESSAGE = 'Para cambiar tu grupo pide ayuda al administrador.'

    def validate(self, attrs):
        # El alumno solo puede completar carrera, cuatrimestre y grupo cuando están vacíos
        cohort_data = validated_cohort_input(self.initial_data)
        profile = getattr(self.instance, 'profile', None)
        for key in cohort_data:
            if profile is not None and getattr(profile, key) is not None:
                raise serializers.ValidationError(self.COHORT_LOCKED_MESSAGE)
        attrs['_cohort'] = cohort_data
        return attrs

    def update(self, instance, validated_data):
        cohort_data = validated_data.pop('_cohort', {})
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        user = super().update(instance, validated_data)
        if cohort_data:
            save_cohort(user, cohort_data)
            from academic.enrollment import enroll_student
            enroll_student(user)
        return user


class CarreraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrera
        fields = ('id', 'nombre', 'clave')
        # La unicidad de clave se valida ya normalizada (validate_clave)
        extra_kwargs = {'clave': {'validators': []}}

    def validate_clave(self, value):
        value = normalizar_clave(value)
        if value and Carrera.objects.filter(clave=value).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError(f'La clave {value} ya está registrada.')
        return value


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
    cuatrimestre = serializers.IntegerField(min_value=1, max_value=9)
    grupo = serializers.IntegerField(min_value=1, max_value=6)

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
                    cuatrimestre=validated_data['cuatrimestre'], grupo=validated_data['grupo'],
                )
        except IntegrityError:
            raise serializers.ValidationError({'matricula': 'Esta matrícula ya está registrada.'})
        return user

    def to_representation(self, instance):
        return ProfileSerializer(instance, context=self.context).data


class PasswordResetRequestSerializer(serializers.Serializer):
    identificador = serializers.CharField(help_text='Matrícula, usuario o email')


class PasswordResetConfirmSerializer(serializers.Serializer):
    INVALID_LINK = 'El enlace no es válido o ya venció. Solicita uno nuevo.'

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        try:
            user_id = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(self.INVALID_LINK)
        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError(self.INVALID_LINK)
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError('Las contraseñas no coinciden.')
        try:
            validate_password(attrs['password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data['user']
        # Cambiar el hash invalida el token automáticamente
        user.set_password(self.validated_data['password'])
        user.save(update_fields=['password'])
        revoke_refresh_tokens(user)
        return user
