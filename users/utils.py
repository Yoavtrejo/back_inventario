from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def enviar_correo_bienvenida(user, raw_password=None):
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