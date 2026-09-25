from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

def enviar_correo_bienvenida(user, raw_password=None, origen='admin'):
    """
    origen='admin': alta por un administrador (incluye la contraseña temporal).
    origen='registro': registro público del alumno; nunca incluye la contraseña.
    """
    if origen == 'registro':
        _enviar_bienvenida_registro(user)
        return

    subject = '¡Bienvenido a SIDERED!'
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [user.email]

    context = {
        'nombre': user.first_name or user.username,
        'username': user.username,
        'password': raw_password,
        'login_url': f'{settings.FRONTEND_URL}/login',
    }

    text_content = f"Hola {context['nombre']},\n\nTu cuenta en SIDERED ha sido creada.\nUsuario: {context['username']}"
    
    html_content = render_to_string('emails/bienvenida.html', context)

    msg = EmailMultiAlternatives(subject, text_content, from_email, to)
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=True)


def _enviar_html_y_texto(subject, template, context, to):
    text_content = render_to_string(f'emails/{template}.txt', context)
    html_content = render_to_string(f'emails/{template}.html', context)
    msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, to)
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=True)


def _enviar_bienvenida_registro(user):
    context = {
        'nombre': user.first_name or user.username,
        'matricula': user.username,
        'login_url': f'{settings.FRONTEND_URL}/login',
        'recuperar_url': f'{settings.FRONTEND_URL}/recuperar',
    }
    _enviar_html_y_texto('SIDERED · ¡Bienvenido a SIDERED!', 'bienvenida_registro', context, [user.email])


def enviar_correo_recuperacion(user):
    """Enlace de un solo uso para restablecer la contraseña (vence según PASSWORD_RESET_TIMEOUT)."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    context = {
        'nombre': user.first_name or user.username,
        'username': user.username,
        'reset_url': f'{settings.FRONTEND_URL}/restablecer?uid={uid}&token={token}',
    }
    _enviar_html_y_texto('SIDERED · Recupera tu contraseña', 'recuperar_contrasena', context, [user.email])
