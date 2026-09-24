"""
Recordatorios de entrega por correo. Idempotente: pensado para correr cada 15 minutos (cron/systemd).

- RECORDATORIO_24H: entre 24 h y 1 h antes de la fecha límite.
- RECORDATORIO_1H: en la última hora.
- VENCIDA: una vez vencida, solo para actividades que vencieron hace 7 días o menos.

Solo se avisa a alumnos del grupo sin entrega propia ni de su equipo. Cada aviso se registra en
NotificationLog después de enviarse; si el envío falla, se reintenta en la siguiente corrida.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone

from academic.models import Activity, NotificationLog, Submission, WorkTeam
from academic.notifications import activity_context, format_time_left, send_student_email

VENTANA_24H = timedelta(hours=24)
VENTANA_1H = timedelta(hours=1)
LIMITE_VENCIDAS = timedelta(days=7)


def current_kind(due_date, now):
    """Aviso que corresponde a este momento; nunca los de ventanas anteriores."""
    if now >= due_date:
        return NotificationLog.Kind.VENCIDA if now - due_date <= LIMITE_VENCIDAS else None
    if now >= due_date - VENTANA_1H:
        return NotificationLog.Kind.RECORDATORIO_1H
    if now >= due_date - VENTANA_24H:
        return NotificationLog.Kind.RECORDATORIO_24H
    return None


def pending_students(activity, kind):
    """Alumnos del grupo sin entrega (propia o de equipo) y sin este aviso ya enviado."""
    submissions = Submission.objects.filter(activity=activity)
    delivered_ids = set(submissions.exclude(student=None).values_list('student_id', flat=True))
    delivered_ids |= set(
        WorkTeam.objects.filter(submissions__activity=activity).values_list('members', flat=True)
    )
    notified_ids = NotificationLog.objects.filter(activity=activity, kind=kind).values_list('user_id', flat=True)
    return (
        activity.group.students.exclude(id__in=delivered_ids)
        .exclude(id__in=notified_ids)
        .exclude(email='')
    )


class Command(BaseCommand):
    help = 'Envía recordatorios de entrega (24 h, 1 h y vencida) a los alumnos que no han entregado.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra a quién se enviaría cada aviso sin enviar ni registrar nada.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()
        activities = Activity.objects.filter(
            due_date__gte=now - LIMITE_VENCIDAS, due_date__lte=now + VENTANA_24H
        ).select_related('group__subject')

        sent = failed = 0
        for activity in activities:
            kind = current_kind(activity.due_date, now)
            if kind is None:
                continue
            base_context = activity_context(activity)
            if kind == NotificationLog.Kind.VENCIDA:
                template = 'entrega_vencida'
                subject = f'Venció la entrega de «{activity.title}»'
            else:
                template = 'recordatorio_entrega'
                time_left = format_time_left(activity.due_date - now)
                base_context['tiempo_restante'] = time_left
                subject = f'Te quedan {time_left} para entregar «{activity.title}»'

            team_member_ids = set()
            if activity.is_team_activity:
                team_member_ids = set(
                    WorkTeam.objects.filter(group=activity.group).values_list('members', flat=True)
                )

            for student in pending_students(activity, kind):
                context = {
                    **base_context,
                    'sin_equipo': activity.is_team_activity and student.id not in team_member_ids,
                }
                if dry_run:
                    self.stdout.write(f'[dry-run] {kind} · {activity.title} → {student.email}')
                    continue
                try:
                    send_student_email(student, subject, template, context, fail_silently=False)
                except Exception as exc:
                    failed += 1
                    self.stderr.write(f'No se pudo enviar {kind} de «{activity.title}» a {student.email}: {exc}')
                    continue
                try:
                    NotificationLog.objects.create(user=student, activity=activity, kind=kind)
                except IntegrityError:
                    pass  # otra corrida simultánea ya lo registró
                sent += 1

        self.stdout.write(self.style.SUCCESS(f'Recordatorios enviados: {sent}. Fallidos: {failed}.'))
