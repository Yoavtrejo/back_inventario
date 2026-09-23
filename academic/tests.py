from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission

User = get_user_model()


def pkt_file(name="practica.pkt"):
    return SimpleUploadedFile(name, b"packet tracer", content_type="application/octet-stream")


class AcademicTestCase(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.docente = User.objects.create_user(username="docente", password="x", is_staff=True)
        self.otro_docente = User.objects.create_user(username="docente2", password="x", is_staff=True)
        self.alumno = User.objects.create_user(username="alumno", password="x")
        self.alumno2 = User.objects.create_user(username="alumno2", password="x")
        self.ajeno = User.objects.create_user(username="ajeno", password="x")

        self.term = Term.objects.create(name="Sep-Dic 2026")
        self.subject = Subject.objects.create(name="Redes")
        self.group = ClassGroup.objects.create(
            name="ISC34", term=self.term, subject=self.subject, teacher=self.docente
        )
        self.group.students.add(self.alumno, self.alumno2)
        self.other_group = ClassGroup.objects.create(
            name="ISC35", term=self.term, subject=self.subject, teacher=self.otro_docente
        )
        self.activity = Activity.objects.create(group=self.group, title="Práctica 1", partial_period=1)
        self.team_activity = Activity.objects.create(
            group=self.group, title="Examen", partial_period=1, is_team_activity=True
        )

    def ids(self, response):
        return sorted(item["id"] for item in response.data["data"])


class ClassGroupPermissionTests(AcademicTestCase):
    def test_groups_are_filtered_by_role(self) -> None:
        url = reverse("classgroup-list")
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.ids(self.client.get(url)), sorted([self.group.id, self.other_group.id]))
        self.client.force_authenticate(user=self.docente)
        self.assertEqual(self.ids(self.client.get(url)), [self.group.id])
        self.client.force_authenticate(user=self.alumno)
        self.assertEqual(self.ids(self.client.get(url)), [self.group.id])

    def test_disponibles_lists_groups_the_alumno_can_join(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        response = self.client.get(reverse("classgroup-list"), {"disponibles": "true"})
        self.assertEqual(self.ids(response), [self.other_group.id])

    def test_only_alumnos_can_join(self) -> None:
        url = reverse("classgroup-join-group", kwargs={"pk": self.other_group.pk})
        self.client.force_authenticate(user=self.alumno)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_200_OK)
        self.assertTrue(self.other_group.students.filter(pk=self.alumno.pk).exists())

        self.client.force_authenticate(user=self.docente)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_only_group_teacher_or_admin_can_edit_or_delete(self) -> None:
        url = reverse("classgroup-detail", kwargs={"pk": self.group.pk})
        self.client.force_authenticate(user=self.otro_docente)
        self.assertEqual(
            self.client.patch(url, data={"name": "X"}, format="json").status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(user=self.alumno)
        self.assertEqual(
            self.client.patch(url, data={"name": "X"}, format="json").status_code, status.HTTP_403_FORBIDDEN
        )
        self.client.force_authenticate(user=self.docente)
        response = self.client.patch(url, data={"name": "ISC34-B", "teacher": self.otro_docente.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "ISC34-B")
        self.assertEqual(self.group.teacher, self.docente)  # un docente no puede reasignar el grupo

    def test_docente_creates_group_as_its_teacher(self) -> None:
        self.client.force_authenticate(user=self.docente)
        response = self.client.post(
            reverse("classgroup-list"),
            data={"name": "ISC36", "term": self.term.id, "subject": self.subject.id,
                  "teacher": self.otro_docente.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClassGroup.objects.get(name="ISC36").teacher, self.docente)

    def test_alumno_can_only_see_own_grades(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        url = reverse("classgroup-get-grades", kwargs={"pk": self.group.pk, "partial": 1})
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
        response = self.client.get(url, {"student_id": self.alumno2.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_grades_include_team_submissions(self) -> None:
        team = WorkTeam.objects.create(group=self.group, name="Equipo 1")
        team.members.add(self.alumno, self.alumno2)
        Submission.objects.create(activity=self.activity, student=self.alumno2, status="Calificado", grade=8)
        Submission.objects.create(
            activity=self.team_activity, student=self.alumno, work_team=team, status="Calificado", grade=10
        )
        self.client.force_authenticate(user=self.docente)
        url = reverse("classgroup-get-grades", kwargs={"pk": self.group.pk, "partial": 1})
        response = self.client.get(url, {"student_id": self.alumno2.id})
        self.assertEqual(response.data["data"]["average_grade"], 9)


class ActivityPermissionTests(AcademicTestCase):
    def test_activities_are_filtered_by_visible_groups(self) -> None:
        other_activity = Activity.objects.create(group=self.other_group, title="Otra", partial_period=1)
        self.client.force_authenticate(user=self.alumno)
        ids = self.ids(self.client.get(reverse("activity-list")))
        self.assertIn(self.activity.id, ids)
        self.assertNotIn(other_activity.id, ids)

    def test_only_group_teacher_or_admin_can_create_activities(self) -> None:
        payload = {"group": self.group.id, "title": "Práctica 2", "partial_period": 1}
        self.client.force_authenticate(user=self.otro_docente)
        self.assertEqual(
            self.client.post(reverse("activity-list"), data=payload).status_code, status.HTTP_403_FORBIDDEN
        )
        self.client.force_authenticate(user=self.alumno)
        self.assertEqual(
            self.client.post(reverse("activity-list"), data=payload).status_code, status.HTTP_403_FORBIDDEN
        )
        self.client.force_authenticate(user=self.docente)
        self.assertEqual(
            self.client.post(reverse("activity-list"), data=payload).status_code, status.HTTP_201_CREATED
        )


class WorkTeamPermissionTests(AcademicTestCase):
    def test_alumno_cannot_create_teams(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        response = self.client.post(
            reverse("workteam-list"),
            data={"group": self.group.id, "name": "E1", "members": [self.alumno.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_teacher_cannot_create_teams_in_group(self) -> None:
        self.client.force_authenticate(user=self.otro_docente)
        response = self.client.post(
            reverse("workteam-list"),
            data={"group": self.group.id, "name": "E1", "members": [self.alumno.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_team_members_are_validated(self) -> None:
        self.client.force_authenticate(user=self.docente)
        url = reverse("workteam-list")
        # Integrante no inscrito en el grupo
        response = self.client.post(
            url, data={"group": self.group.id, "name": "E1", "members": [self.ajeno.id]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Equipo válido
        response = self.client.post(
            url, data={"group": self.group.id, "name": "E1", "members": [self.alumno.id]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Mismo alumno en dos equipos del grupo
        response = self.client.post(
            url, data={"group": self.group.id, "name": "E2", "members": [self.alumno.id]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_team_max_seven_members(self) -> None:
        extra = [User.objects.create_user(username=f"a{i}", password="x") for i in range(8)]
        self.group.students.add(*extra)
        self.client.force_authenticate(user=self.docente)
        response = self.client.post(
            reverse("workteam-list"),
            data={"group": self.group.id, "name": "E1", "members": [u.id for u in extra]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(WorkTeam.objects.exists())

    def test_alumno_only_sees_own_teams(self) -> None:
        mine = WorkTeam.objects.create(group=self.group, name="E1")
        mine.members.add(self.alumno)
        other = WorkTeam.objects.create(group=self.group, name="E2")
        other.members.add(self.alumno2)
        self.client.force_authenticate(user=self.alumno)
        self.assertEqual(self.ids(self.client.get(reverse("workteam-list"))), [mine.id])


class SubmissionPermissionTests(AcademicTestCase):
    def submit(self, user, activity, **extra):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("submission-list"),
            data={"activity": activity.id, "student_file": pkt_file(), **extra},
            format="multipart",
        )

    def test_enrolled_alumno_can_submit_once(self) -> None:
        response = self.submit(self.alumno, self.activity, grade="10", status="Calificado")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        submission = Submission.objects.get()
        self.assertEqual(submission.student, self.alumno)
        self.assertEqual(submission.status, "Entregado")
        self.assertIsNone(submission.grade)
        self.assertEqual(self.submit(self.alumno, self.activity).status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_enrolled_or_staff_cannot_submit(self) -> None:
        self.assertEqual(self.submit(self.ajeno, self.activity).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.submit(self.docente, self.activity).status_code, status.HTTP_403_FORBIDDEN)

    def test_team_activity_requires_own_team_and_one_submission_per_team(self) -> None:
        team = WorkTeam.objects.create(group=self.group, name="E1")
        team.members.add(self.alumno, self.alumno2)
        self.assertEqual(self.submit(self.alumno, self.team_activity).status_code, status.HTTP_400_BAD_REQUEST)

        other_team = WorkTeam.objects.create(group=self.group, name="E2")
        response = self.submit(self.alumno, self.team_activity, work_team=other_team.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.submit(self.alumno, self.team_activity, work_team=team.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.submit(self.alumno2, self.team_activity, work_team=team.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submissions_are_filtered_by_role(self) -> None:
        team = WorkTeam.objects.create(group=self.group, name="E1")
        team.members.add(self.alumno, self.alumno2)
        own = Submission.objects.create(activity=self.activity, student=self.alumno)
        team_sub = Submission.objects.create(activity=self.team_activity, student=self.alumno2, work_team=team)
        other = Submission.objects.create(activity=self.activity, student=self.alumno2)
        url = reverse("submission-list")

        self.client.force_authenticate(user=self.alumno)
        self.assertEqual(self.ids(self.client.get(url)), sorted([own.id, team_sub.id]))
        self.client.force_authenticate(user=self.otro_docente)
        self.assertEqual(self.ids(self.client.get(url)), [])
        self.client.force_authenticate(user=self.docente)
        self.assertEqual(self.ids(self.client.get(url)), sorted([own.id, team_sub.id, other.id]))

    def test_alumno_cannot_grade(self) -> None:
        submission = Submission.objects.create(activity=self.activity, student=self.alumno)
        self.client.force_authenticate(user=self.alumno)
        url = reverse("submission-detail", kwargs={"pk": submission.pk})
        response = self.client.patch(url, data={"grade": "10", "status": "Calificado"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        submission.refresh_from_db()
        self.assertIsNone(submission.grade)
        self.assertEqual(submission.status, "Entregado")

    def test_teacher_grades_within_range(self) -> None:
        submission = Submission.objects.create(activity=self.activity, student=self.alumno)
        url = reverse("submission-detail", kwargs={"pk": submission.pk})
        self.client.force_authenticate(user=self.otro_docente)
        self.assertEqual(
            self.client.patch(url, data={"grade": "9"}, format="json").status_code, status.HTTP_404_NOT_FOUND
        )
        self.client.force_authenticate(user=self.docente)
        self.assertEqual(
            self.client.patch(url, data={"grade": "11"}, format="json").status_code, status.HTTP_400_BAD_REQUEST
        )
        response = self.client.patch(url, data={"grade": "9.5", "status": "Calificado"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "Calificado")
        submission.refresh_from_db()
        self.assertEqual(float(submission.grade), 9.5)

    def test_alumno_replaces_file_until_graded(self) -> None:
        submission = Submission.objects.create(activity=self.activity, student=self.alumno, status="En revisión")
        url = reverse("submission-detail", kwargs={"pk": submission.pk})
        self.client.force_authenticate(user=self.alumno)
        response = self.client.patch(url, data={"student_file": pkt_file("v2.pkt")}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "Entregado")
        self.assertIn("v2", submission.student_file.name)

        Submission.objects.filter(pk=submission.pk).update(status="Calificado", grade=8)
        response = self.client.patch(url, data={"student_file": pkt_file("v3.pkt")}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_alumno_cannot_delete_submission(self) -> None:
        submission = Submission.objects.create(activity=self.activity, student=self.alumno)
        self.client.force_authenticate(user=self.alumno)
        response = self.client.delete(reverse("submission-detail", kwargs={"pk": submission.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
