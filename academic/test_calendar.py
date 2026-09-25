from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CalendarEvent, Subject, Term

User = get_user_model()


class CalendarTestCase(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.docente = User.objects.create_user(username="docente", password="x", is_staff=True)
        self.alumno = User.objects.create_user(username="alumno", password="x")


class TermTests(CalendarTestCase):
    def test_only_one_active_term(self) -> None:
        first = Term.objects.create(name="May-Ago 2026", is_active=True)
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("term-list"),
            data={"name": "Sep-Dic 2026", "start_date": "2026-09-01", "end_date": "2026-12-15", "is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            set(response.data["data"]), {"id", "name", "description", "start_date", "end_date", "is_active"}
        )
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(Term.objects.filter(is_active=True).count(), 1)

        self.client.patch(reverse("term-detail", kwargs={"pk": first.pk}), data={"is_active": True}, format="json")
        self.assertEqual(list(Term.objects.filter(is_active=True).values_list("pk", flat=True)), [first.pk])

    def test_end_date_must_be_after_start_date(self) -> None:
        self.client.force_authenticate(user=self.admin)
        for end in ("2026-08-31", "2026-09-01"):
            response = self.client.post(
                reverse("term-list"),
                data={"name": f"T{end}", "start_date": "2026-09-01", "end_date": end},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        term = Term.objects.create(name="Sep-Dic", start_date="2026-09-01", end_date="2026-12-15")
        response = self.client.patch(
            reverse("term-detail", kwargs={"pk": term.pk}), data={"end_date": "2026-08-01"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_terms_and_subjects_write_only_admin(self) -> None:
        term = Term.objects.create(name="Sep-Dic")
        subject = Subject.objects.create(name="Redes")
        for user in (self.docente, self.alumno):
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get(reverse("term-list")).status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get(reverse("subject-list")).status_code, status.HTTP_200_OK)
            self.assertEqual(
                self.client.post(reverse("term-list"), data={"name": "X"}, format="json").status_code, 403
            )
            self.assertEqual(
                self.client.post(reverse("subject-list"), data={"name": "X"}, format="json").status_code, 403
            )
            self.assertEqual(self.client.delete(reverse("term-detail", kwargs={"pk": term.pk})).status_code, 403)
            self.assertEqual(
                self.client.patch(reverse("subject-detail", kwargs={"pk": subject.pk}), data={"name": "Y"},
                                  format="json").status_code, 403
            )
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(
            self.client.post(reverse("subject-list"), data={"name": "Seguridad"}, format="json").status_code, 201
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse("term-list")).status_code, status.HTTP_401_UNAUTHORIZED)


class CalendarEventTests(CalendarTestCase):
    def create(self, **data):
        self.client.force_authenticate(user=self.admin)
        return self.client.post(reverse("calendar-event-list"), data=data, format="json")

    def ids(self, **params):
        self.client.force_authenticate(user=self.alumno)
        response = self.client.get(reverse("calendar-event-list"), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [event["id"] for event in response.data["data"]]

    def test_admin_creates_event(self) -> None:
        term = Term.objects.create(name="Sep-Dic")
        response = self.create(title="Día de muertos", start_date="2026-11-02", kind="festivo", term=term.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual(
            set(data), {"id", "title", "description", "start_date", "end_date", "kind", "term", "created_at"}
        )
        self.assertIsNone(data["end_date"])
        self.assertEqual(CalendarEvent.objects.get().created_by, self.admin)
        self.assertEqual(self.create(title="Sin tipo", start_date="2026-11-03").data["data"]["kind"], "evento")

    def test_event_validations(self) -> None:
        response = self.create(title="Exámenes", start_date="2026-12-10", end_date="2026-12-09", kind="examenes")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.create(title="X", start_date="2026-12-10", kind="otro").status_code, 400)
        self.assertEqual(self.create(start_date="2026-12-10").status_code, 400)
        self.assertEqual(self.create(title="x" * 121, start_date="2026-12-10").status_code, 400)
        self.assertEqual(
            self.create(title="Un día", start_date="2026-12-10", end_date="2026-12-10").status_code, 201
        )

    def test_events_write_only_admin(self) -> None:
        event = CalendarEvent.objects.create(title="Evento", start_date="2026-10-01")
        for user in (self.docente, self.alumno):
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get(reverse("calendar-event-list")).status_code, 200)
            self.assertEqual(
                self.client.post(reverse("calendar-event-list"), data={"title": "X", "start_date": "2026-10-02"},
                                 format="json").status_code, 403
            )
            detail = reverse("calendar-event-detail", kwargs={"pk": event.pk})
            self.assertEqual(self.client.patch(detail, data={"title": "Y"}, format="json").status_code, 403)
            self.assertEqual(self.client.delete(detail).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendar-event-list")).status_code, 401)

    def test_range_filter_includes_overlapping_multi_day_events(self) -> None:
        before = CalendarEvent.objects.create(title="Antes", start_date="2026-09-20", end_date="2026-09-28")
        spans_start = CalendarEvent.objects.create(title="Cruza inicio", start_date="2026-09-28", end_date="2026-10-03")
        inside = CalendarEvent.objects.create(title="Dentro", start_date="2026-10-10")
        spans_all = CalendarEvent.objects.create(title="Abarca", start_date="2026-09-15", end_date="2026-11-15")
        spans_end = CalendarEvent.objects.create(title="Cruza fin", start_date="2026-10-30", end_date="2026-11-05")
        CalendarEvent.objects.create(title="Después", start_date="2026-11-01")
        CalendarEvent.objects.create(title="Un día antes", start_date="2026-09-30")

        self.assertEqual(
            self.ids(desde="2026-10-01", hasta="2026-10-31"),
            [spans_all.id, spans_start.id, inside.id, spans_end.id],
        )
        self.assertEqual(len(self.ids()), 7)
        self.assertIn(before.id, self.ids(hasta="2026-09-25"))

    def test_invalid_range_params(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        url = reverse("calendar-event-list")
        self.assertEqual(self.client.get(url, {"desde": "01/10/2026"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"desde": "2026-10-02", "hasta": "2026-10-01"}).status_code, 400)
