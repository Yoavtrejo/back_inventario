from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission, NotificationLog

User = get_user_model()


class NotificationTestMixin:
    def build_fixtures(self) -> None:
        self.docente = User.objects.create_user(username="docente", email="docente@example.com", password="x",
                                                is_staff=True)
        self.alumno = User.objects.create_user(username="alumno", email="alumno@example.com", password="x",
                                               first_name="Ana")
        self.alumno2 = User.objects.create_user(username="alumno2", email="alumno2@example.com", password="x")
        self.sin_email = User.objects.create_user(username="sinemail", email="", password="x")
        self.group = ClassGroup.objects.create(
            name="ISC34", term=Term.objects.create(name="Sep-Dic 2026"),
            subject=Subject.objects.create(name="Redes"), teacher=self.docente,
        )
        self.group.students.add(self.alumno, self.alumno2, self.sin_email)

    def activity(self, due_in, **extra):
        return Activity.objects.create(
            group=self.group, title="Práctica VLAN", partial_period=1,
            due_date=timezone.now() + due_in, **extra
        )

    def recipients(self):
        return sorted(address for message in mail.outbox for address in message.to)


@override_settings(FRONTEND_URL="http://front.test")
class ReminderCommandTests(NotificationTestMixin, TestCase):
    def setUp(self) -> None:
        self.build_fixtures()

    def run_command(self, now=None):
        output = StringIO()
        if now is None:
            call_command("enviar_recordatorios", stdout=output, stderr=output)
        else:
            with mock.patch("academic.management.commands.enviar_recordatorios.timezone.now", return_value=now):
                call_command("enviar_recordatorios", stdout=output, stderr=output)
        return output.getvalue()

    def test_24h_and_1h_reminders_in_their_windows_and_idempotent(self) -> None:
        activity = self.activity(timedelta(hours=23, minutes=30))
        self.run_command()
        self.assertEqual(self.recipients(), ["alumno2@example.com", "alumno@example.com"])
        message = mail.outbox[0]
        self.assertTrue(message.subject.startswith("SIDERED · "))
        self.assertIn("te quedan 23 h", message.body)
        self.assertIn("Redes", message.body)
        self.assertIn("ISC34", message.body)
        self.assertIn(timezone.localtime(activity.due_date).strftime("%d/%m/%Y %H:%M"), message.body)
        self.assertIn("http://front.test/alumno/actividades", message.body)
        self.assertEqual(message.alternatives[0][1], "text/html")

        self.run_command()
        self.assertEqual(len(mail.outbox), 2)  # idempotente

        self.run_command(now=activity.due_date - timedelta(minutes=30))
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn("te quedan 30 min", mail.outbox[-1].body)
        self.run_command(now=activity.due_date - timedelta(minutes=15))
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(
            NotificationLog.objects.filter(activity=activity).count(), 4
        )

    def test_activity_created_inside_last_hour_only_sends_1h(self) -> None:
        activity = self.activity(timedelta(minutes=30))
        self.run_command()
        kinds = set(NotificationLog.objects.filter(activity=activity).values_list("kind", flat=True))
        self.assertEqual(kinds, {"RECORDATORIO_1H"})
        self.assertEqual(len(mail.outbox), 2)

    def test_nothing_sent_outside_windows(self) -> None:
        self.activity(timedelta(days=2))
        Activity.objects.create(group=self.group, title="Sin fecha", partial_period=1)
        self.run_command()
        self.assertEqual(mail.outbox, [])

    def test_overdue_sent_once_and_not_for_old_activities(self) -> None:
        activity = self.activity(timedelta(hours=-2))
        self.activity(timedelta(days=-8))
        self.run_command()
        self.assertEqual(self.recipients(), ["alumno2@example.com", "alumno@example.com"])
        self.assertIn("quedará marcada como tardía", mail.outbox[0].body)
        self.run_command()
        self.run_command(now=activity.due_date + timedelta(days=3))
        self.assertEqual(len(mail.outbox), 2)

    def test_students_who_submitted_are_skipped(self) -> None:
        activity = self.activity(timedelta(hours=5))
        Submission.objects.create(activity=activity, student=self.alumno)
        self.run_command()
        self.assertEqual(self.recipients(), ["alumno2@example.com"])

    def test_team_submission_covers_all_members_and_teamless_students_are_warned(self) -> None:
        activity = self.activity(timedelta(hours=5), is_team_activity=True)
        extra = User.objects.create_user(username="alumno3", email="alumno3@example.com", password="x")
        self.group.students.add(extra)
        team = WorkTeam.objects.create(group=self.group, name="E1")
        team.members.add(self.alumno, self.alumno2)
        Submission.objects.create(activity=activity, student=self.alumno2, work_team=team)
        self.run_command()
        self.assertEqual(self.recipients(), ["alumno3@example.com"])
        self.assertIn("aún no tienes equipo", mail.outbox[0].body)

    def test_team_members_without_submission_are_reminded_without_note(self) -> None:
        activity = self.activity(timedelta(hours=5), is_team_activity=True)
        team = WorkTeam.objects.create(group=self.group, name="E1")
        team.members.add(self.alumno, self.alumno2)
        self.run_command()
        self.assertEqual(self.recipients(), ["alumno2@example.com", "alumno@example.com"])
        self.assertNotIn("aún no tienes equipo", mail.outbox[0].body)

    def test_failed_send_is_not_logged_and_retried(self) -> None:
        activity = self.activity(timedelta(hours=5))
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("SMTP caído")):
            output = self.run_command()
        self.assertIn("Fallidos: 2", output)
        self.assertFalse(NotificationLog.objects.filter(activity=activity).exists())
        self.run_command()
        self.assertEqual(len(mail.outbox), 2)

    def test_dry_run_sends_and_logs_nothing(self) -> None:
        self.activity(timedelta(hours=5))
        output = StringIO()
        call_command("enviar_recordatorios", "--dry-run", stdout=output)
        self.assertIn("alumno@example.com", output.getvalue())
        self.assertEqual(mail.outbox, [])
        self.assertFalse(NotificationLog.objects.exists())


class SubmissionStatusEmailTests(NotificationTestMixin, APITestCase):
    def setUp(self) -> None:
        self.build_fixtures()
        self.activity_obj = self.activity(timedelta(days=3))
        self.submission = Submission.objects.create(activity=self.activity_obj, student=self.alumno)
        self.url = reverse("submission-detail", kwargs={"pk": self.submission.pk})
        self.client.force_authenticate(user=self.docente)

    def patch(self, data, url=None):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(url or self.url, data=data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_en_revision_and_calificado_send_emails(self) -> None:
        self.patch({"status": "En revisión"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "SIDERED · Tu entrega de «Práctica VLAN» está en revisión")

        self.patch({"status": "Calificado", "grade": "9.50"})
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].subject, "SIDERED · Tu actividad «Práctica VLAN» fue calificada: 9.5/10")
        self.assertIn("9.5/10", mail.outbox[1].body)

        # Cambio de calificación de una entrega ya calificada
        self.patch({"grade": "10"})
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("10/10", mail.outbox[2].subject)

    def test_patch_without_status_or_grade_change_sends_nothing(self) -> None:
        self.patch({})
        self.patch({"status": "Entregado"})
        self.patch({"status": "En revisión"})
        self.patch({"status": "En revisión"})
        self.assertEqual(len(mail.outbox), 1)

    def test_team_submission_notifies_all_members(self) -> None:
        team_activity = self.activity(timedelta(days=3), is_team_activity=True)
        team = WorkTeam.objects.create(group=self.group, name="E1")
        team.members.add(self.alumno, self.alumno2, self.sin_email)
        submission = Submission.objects.create(activity=team_activity, student=self.alumno, work_team=team)
        self.patch({"status": "Calificado", "grade": "8"},
                   url=reverse("submission-detail", kwargs={"pk": submission.pk}))
        self.assertEqual(self.recipients(), ["alumno2@example.com", "alumno@example.com"])
        self.assertIn("E1", mail.outbox[0].body)

    def test_student_without_email_does_not_fail(self) -> None:
        submission = Submission.objects.create(activity=self.activity_obj, student=self.sin_email)
        self.patch({"status": "Calificado", "grade": "7"},
                   url=reverse("submission-detail", kwargs={"pk": submission.pk}))
        self.assertEqual(mail.outbox, [])

    def test_smtp_failure_does_not_break_grading(self) -> None:
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("SMTP caído")):
            self.patch({"status": "Calificado", "grade": "6"})
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, "Calificado")
