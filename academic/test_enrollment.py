from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import Carrera, UserProfile
from .models import ClassGroup, Subject, Term

User = get_user_model()


def alumno(username, carrera, cuatrimestre, grupo):
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password="x")
    UserProfile.objects.create(user=user, matricula=username, carrera=carrera, cuatrimestre=cuatrimestre, grupo=grupo)
    return user


class EnrollmentTestCase(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.docente = User.objects.create_user(username="docente", password="x", is_staff=True)
        self.isc = Carrera.objects.create(nombre="Ingeniería en Sistemas Computacionales", clave="isc ")
        self.tiid = Carrera.objects.create(nombre="Tecnologías de la Información")  # sin clave
        self.term = Term.objects.create(name="Sep-Dic 2026", is_active=True)
        self.redes = Subject.objects.create(name="Redes")
        self.bd = Subject.objects.create(name="Bases de datos")

    def cohort_group(self, subject, cuatrimestre=3, grupo=4, term=None, name=None):
        return ClassGroup.objects.create(
            name=name or f"ISC{cuatrimestre}{grupo}", term=term or self.term, subject=subject,
            teacher=self.docente, carrera=self.isc, cuatrimestre=cuatrimestre, grupo=grupo,
        )

    def group_ids(self, user):
        return sorted(user.enrolled_groups.values_list("id", flat=True))


class CarreraTests(EnrollmentTestCase):
    def test_clave_is_normalized_and_exposed(self) -> None:
        self.assertEqual(self.isc.clave, "ISC")
        response = self.client.get(reverse("carrera-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn({"id": self.isc.id, "nombre": self.isc.nombre, "clave": "ISC"}, response.data["data"])

    def test_carreras_write_only_admin(self) -> None:
        url = reverse("carrera-list")
        self.assertEqual(self.client.post(url, data={"nombre": "X"}, format="json").status_code, 401)
        self.client.force_authenticate(user=self.docente)
        self.assertEqual(self.client.post(url, data={"nombre": "X"}, format="json").status_code, 403)
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            reverse("carrera-detail", kwargs={"pk": self.tiid.pk}), data={"clave": " tiid"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["clave"], "TIID")
        response = self.client.post(url, data={"nombre": "Otra", "clave": "Isc"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_carrera_in_use_is_400(self) -> None:
        alumno("a1", self.isc, 3, 4)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(reverse("carrera-detail", kwargs={"pk": self.isc.pk}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tiene alumnos o grupos", response.data["message"])
        unused = Carrera.objects.create(nombre="Sin uso")
        self.assertEqual(self.client.delete(reverse("carrera-detail", kwargs={"pk": unused.pk})).status_code, 204)


class RegisterEnrollmentTests(EnrollmentTestCase):
    def payload(self, **extra):
        return {
            "first_name": "Luis", "last_name": "Pérez", "matricula": "2230001", "email": "luis@example.com",
            "password": "Segura#2026", "password_confirm": "Segura#2026", "carrera": self.isc.id,
            "cuatrimestre": 3, "grupo": 4, **extra,
        }

    def test_register_enrolls_only_in_cohort_groups_of_active_term(self) -> None:
        redes = self.cohort_group(self.redes)
        bd = self.cohort_group(self.bd)
        self.cohort_group(self.redes, grupo=5)  # otra cohorte
        old_term = Term.objects.create(name="May-Ago 2026")
        self.cohort_group(self.redes, term=old_term)  # misma cohorte, otro term
        ClassGroup.objects.create(name="Libre", term=self.term, subject=self.redes, teacher=self.docente)

        response = self.client.post(reverse("register"), data=self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual((data["cuatrimestre"], data["grupo"], data["grupo_escolar"]), (3, 4, "ISC34"))
        self.assertEqual((data["carrera_id"], data["carrera_clave"]), (self.isc.id, "ISC"))
        self.assertEqual(self.group_ids(User.objects.get(username="2230001")), sorted([redes.id, bd.id]))

    def test_register_requires_valid_cuatrimestre_and_grupo(self) -> None:
        for extra, field in (({"cuatrimestre": 10}, "cuatrimestre"), ({"grupo": 7}, "grupo"),
                             ({"cuatrimestre": 0}, "cuatrimestre")):
            response = self.client.post(reverse("register"), data=self.payload(**extra), format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertTrue(response.data["message"].startswith(f"{field}: "))
        payload = self.payload()
        del payload["grupo"]
        self.assertEqual(self.client.post(reverse("register"), data=payload, format="json").status_code, 400)


class ClassGroupCohortTests(EnrollmentTestCase):
    def create(self, **data):
        self.client.force_authenticate(user=self.docente)
        return self.client.post(reverse("classgroup-list"), data=data, format="json")

    def test_docente_creates_cohort_group_and_students_are_enrolled(self) -> None:
        a1 = alumno("a1", self.isc, 3, 4)
        a2 = alumno("a2", self.isc, 3, 4)
        alumno("otro", self.isc, 3, 5)
        response = self.create(subject=self.redes.id, carrera=self.isc.id, cuatrimestre=3, grupo=4, name="ignorado")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual(data["name"], "ISC34")
        self.assertEqual(data["term"], self.term.id)
        self.assertEqual(data["carrera_clave"], "ISC")
        self.assertEqual(data["students_count"], 2)
        self.assertEqual(sorted(data["students"]), sorted([a1.id, a2.id]))
        self.assertEqual(sorted(s["grupo_escolar"] for s in data["students_detail"]), ["ISC34", "ISC34"])
        self.assertEqual(ClassGroup.objects.get(pk=data["id"]).teacher, self.docente)

    def test_cohort_validations(self) -> None:
        response = self.create(subject=self.redes.id, carrera=self.tiid.id, cuatrimestre=3, grupo=4)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["message"],
            "La carrera Tecnologías de la Información no tiene clave; pídele al administrador que la registre.",
        )
        response = self.create(subject=self.redes.id, carrera=self.isc.id, cuatrimestre=3)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.create(subject=self.redes.id, carrera=self.isc.id, cuatrimestre=10,
                                     grupo=4).status_code, 400)
        self.assertEqual(self.create(subject=self.redes.id, carrera=self.isc.id, cuatrimestre=3,
                                     grupo=7).status_code, 400)
        self.assertEqual(self.create(subject=self.redes.id, carrera=self.isc.id, cuatrimestre=3,
                                     grupo=4).status_code, 201)
        response = self.create(subject=self.redes.id, carrera=self.isc.id, cuatrimestre=3, grupo=4)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Ya existe el grupo ISC34 de Redes en Sep-Dic 2026.")

    def test_legacy_group_with_free_name_still_works(self) -> None:
        response = self.create(name="Grupo A", subject=self.redes.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["data"]["carrera"])
        self.assertEqual(self.create(subject=self.bd.id).status_code, 400)

    def test_filters(self) -> None:
        g34 = self.cohort_group(self.redes)
        g35 = self.cohort_group(self.redes, grupo=5)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("classgroup-list"), {"carrera": self.isc.id, "grupo": 5})
        self.assertEqual([g["id"] for g in response.data["data"]], [g35.id])
        response = self.client.get(reverse("classgroup-list"), {"cuatrimestre": 3})
        self.assertEqual(sorted(g["id"] for g in response.data["data"]), sorted([g34.id, g35.id]))


class AdminCohortChangeTests(EnrollmentTestCase):
    def test_admin_moves_student_to_new_cohort_keeping_manual_enrollments(self) -> None:
        student = alumno("a1", self.isc, 3, 4)
        old_redes = self.cohort_group(self.redes)
        old_bd = self.cohort_group(self.bd)
        new_redes = self.cohort_group(self.redes, grupo=5)
        recursa = self.cohort_group(self.redes, cuatrimestre=2, grupo=4)
        for group in (old_redes, old_bd, recursa):
            group.students.add(student)

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(reverse("user-detail", kwargs={"pk": student.pk}), data={"grupo": 5},
                                     format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["grupo_escolar"], "ISC35")
        self.assertEqual(self.group_ids(student), sorted([new_redes.id, recursa.id]))

    def test_admin_sets_cohort_for_user_without_profile(self) -> None:
        user = User.objects.create_user(username="sinperfil", password="x")
        group = self.cohort_group(self.redes)
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            reverse("user-detail", kwargs={"pk": user.pk}),
            data={"carrera": self.isc.id, "cuatrimestre": 3, "grupo": 4}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["matricula"], "sinperfil")
        self.assertEqual(self.group_ids(user), [group.id])
        response = self.client.patch(reverse("user-detail", kwargs={"pk": user.pk}), data={"grupo": 9},
                                     format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProfileCohortTests(EnrollmentTestCase):
    def test_profile_completes_cohort_once(self) -> None:
        user = User.objects.create_user(username="2230009", password="x")
        UserProfile.objects.create(user=user, matricula="2230009", carrera=self.isc)
        group = self.cohort_group(self.redes)
        self.client.force_authenticate(user=user)
        url = reverse("user-profile")
        response = self.client.patch(url, data={"carrera": self.tiid.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["non_field_errors"], ["Para cambiar tu grupo pide ayuda al administrador."])

        response = self.client.patch(url, data={"cuatrimestre": 3, "grupo": 4}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["grupo_escolar"], "ISC34")
        self.assertEqual(self.group_ids(user), [group.id])

        response = self.client.patch(url, data={"grupo": 5}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["non_field_errors"], ["Para cambiar tu grupo pide ayuda al administrador."])
        response = self.client.patch(url, data={"first_name": "Ana"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TermActivationTests(EnrollmentTestCase):
    def test_activating_term_enrolls_by_cohort(self) -> None:
        a1 = alumno("a1", self.isc, 4, 1)
        alumno("a2", self.isc, 4, 2)
        next_term = Term.objects.create(name="Ene-Abr 2027")
        group = self.cohort_group(self.redes, cuatrimestre=4, grupo=1, term=next_term)
        self.assertEqual(group.students.count(), 0)  # term inactivo: no inscribe al crear

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(reverse("term-detail", kwargs={"pk": next_term.pk}), data={"is_active": True},
                                     format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(list(group.students.values_list("id", flat=True)), [a1.id])
