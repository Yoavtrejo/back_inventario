"""Validaciones de configuración que se ejecutan al cargar settings."""

from django.core.exceptions import ImproperlyConfigured

# Clave de desarrollo publicada en el repositorio: nunca debe usarse en producción
INSECURE_SECRET_KEY = 'django-insecure-zhljik@=dqirx#b($)zp+!^=n@7+m-6dzk++fb831h-f9olmcj'


def check_secret_key(secret_key: str, debug: bool) -> None:
    if not debug and (not secret_key or secret_key == INSECURE_SECRET_KEY):
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY debe definirse en .env cuando DJANGO_DEBUG=False.'
        )


def env_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]
