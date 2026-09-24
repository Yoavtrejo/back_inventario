"""
Correos al alumno sobre sus actividades: cambios de estado de entregas y recordatorios de fecha límite.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

SUBJECT_PREFIX = 'SIDERED · '


def activity_context(activity):
    group = activity.group
    context = {
        'actividad': activity.title,
        'materia': group.subject.name,
        'grupo': group.name,
        'fecha_limite': None,
    }
    if activity.due_date:
        context['fecha_limite'] = timezone.localtime(activity.due_date).strftime('%d/%m/%Y %H:%M')
    return context


def format_grade(grade):
    return ('%.2f' % grade).rstrip('0').rstrip('.')


def format_time_left(delta: timedelta) -> str:
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    if total_minutes >= 60:
        return f'{total_minutes // 60} h'
    return f'{total_minutes} min'


def send_student_email(user, subject, template, context, fail_silently=True) -> bool:
    """Envía un correo al usuario con la plantilla emails/<template>.html/.txt. Devuelve True si se envió."""
    if not user.email:
        return False
    context = {
        'nombre': user.first_name or user.username,
        'activities_url': f'{settings.FRONTEND_URL}/alumno/actividades',
        **context,
    }
    text_content = render_to_string(f'emails/{template}.txt', context)
    html_content = render_to_string(f'emails/{template}.html', context)
    message = EmailMultiAlternatives(
        SUBJECT_PREFIX + subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email]
    )
    message.attach_alternative(html_content, 'text/html')
    return message.send(fail_silently=fail_silently) > 0


def submission_recipients(submission):
    """El alumno que entregó o, si es entrega de equipo, todos sus integrantes."""
    if submission.work_team_id:
        return list(submission.work_team.members.all())
    return [submission.student] if submission.student else []


def notify_submission_status_change(submission, old_status, old_grade):
    """
    Avisa al alumno (o al equipo) cuando su entrega pasa a 'En revisión' o se califica
    (incluye cambios de calificación de una entrega ya calificada).
    """
    if submission.status == 'En revisión' and old_status != 'En revisión':
        template = 'entrega_en_revision'
        subject = f'Tu entrega de «{submission.activity.title}» está en revisión'
    elif submission.status == 'Calificado' and (old_status != 'Calificado' or old_grade != submission.grade):
        template = 'entrega_calificada'
        grade = format_grade(submission.grade) if submission.grade is not None else 'sin calificación'
        subject = f'Tu actividad «{submission.activity.title}» fue calificada: {grade}/10'
    else:
        return

    context = activity_context(submission.activity)
    context['equipo'] = submission.work_team.name if submission.work_team_id else None
    if template == 'entrega_calificada':
        context['calificacion'] = grade

    for user in submission_recipients(submission):
        try:
            send_student_email(user, subject, template, context, fail_silently=True)
        except Exception:
            # Un fallo al armar o enviar el correo nunca debe romper la petición del docente
            logger.exception('No se pudo notificar la entrega %s a %s', submission.pk, user.pk)
