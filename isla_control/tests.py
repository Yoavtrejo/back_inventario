import datetime as dt
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from isla_control.models import Isla, Reservacion

User = get_user_model()


class IslaControlApiTests(APITestCase):
    def setUp(self) -> None:
        self.regular_user = User.objects.create_user(
            username="student1",
            email="student1@example.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            username="student2",
            email="student2@example.com",
            password="password456",
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpassword",
        )
        # Create a default island
        self.isla1 = Isla.objects.create(
            numero_isla=1,
            equipos_computo=4,
            switches=1,
            routers=0,
            otros_componentes={"laptops": 2}
        )

    def test_admin_can_create_and_manage_islas(self) -> None:
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("isla-list"),
            data={
                "numero_isla": 2,
                "equipos_computo": 6,
                "switches": 2,
                "routers": 1,
                "otros_componentes": {"racks_adicionales": 1}
            },
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Isla.objects.count(), 2)

    def test_regular_user_cannot_create_islas(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post(
            reverse("isla-list"),
            data={
                "numero_isla": 2,
                "equipos_computo": 6,
            },
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_can_reserve_isla_max_4_hours(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        fecha_reserva = dt.date.today()
        
        # Valid reservation (2 hours)
        response = self.client.post(
            reverse("reservacion-list"),
            data={
                "isla": self.isla1.id,
                "fecha_reserva": fecha_reserva.isoformat(),
                "hora_inicio": "10:00:00",
                "duracion_horas": 2
            },
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Isla state changes to Reservada
        self.isla1.refresh_from_db()
        self.assertEqual(self.isla1.estado, 'Reservada')

        # Invalid reservation (> 4 hours)
        response = self.client.post(
            reverse("reservacion-list"),
            data={
                "isla": self.isla1.id,
                "fecha_reserva": fecha_reserva.isoformat(),
                "hora_inicio": "14:00:00",
                "duracion_horas": 5
            },
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overlapping_reservations_are_rejected(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        fecha_reserva = dt.date.today()

        # Reserve island from 10:00 to 12:00
        Reservacion.objects.create(
            isla=self.isla1,
            alumno=self.regular_user,
            fecha_reserva=fecha_reserva,
            hora_inicio="10:00:00",
            duracion_horas=2
        )

        # Attempt to reserve same island from 11:00 to 13:00 (overlaps)
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(
            reverse("reservacion-list"),
            data={
                "isla": self.isla1.id,
                "fecha_reserva": fecha_reserva.isoformat(),
                "hora_inicio": "11:00:00",
                "duracion_horas": 2
            },
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_scan_qr_starts_timer(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        fecha_reserva = dt.date.today()

        # Create reservation
        res = Reservacion.objects.create(
            isla=self.isla1,
            alumno=self.regular_user,
            fecha_reserva=fecha_reserva,
            hora_inicio="09:00:00",
            duracion_horas=3
        )
        
        # Scan with wrong token
        response = self.client.post(
            reverse("reservacion-escanear-qr"),
            data={"qr_token": "00000000-0000-0000-0000-000000000000"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Scan with correct token
        response = self.client.post(
            reverse("reservacion-escanear-qr"),
            data={"qr_token": str(self.isla1.qr_token)},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify timer started
        res.refresh_from_db()
        self.assertIsNotNone(res.hora_escaneo_inicio)

    def test_generate_qr_endpoint(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(
            reverse("isla-generar-qr", kwargs={"pk": self.isla1.pk})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_tolerance_window_expiration(self) -> None:
        # Create a reservation starting now (should be active and island is Reservada)
        ahora = dt.datetime.now()
        res = Reservacion.objects.create(
            isla=self.isla1,
            alumno=self.regular_user,
            fecha_reserva=ahora.date(),
            hora_inicio=ahora.time(),
            duracion_horas=1
        )
        
        # Initial status should be Reservada
        self.isla1.refresh_from_db()
        self.assertEqual(self.isla1.estado, 'Reservada')

        # Simulate passage of time: update the start time to 11 minutes ago in DB directly
        hace_11_minutos = ahora - dt.timedelta(minutes=11)
        Reservacion.objects.filter(id=res.id).update(
            fecha_reserva=hace_11_minutos.date(),
            hora_inicio=hace_11_minutos.time()
        )

        # Triggering view list query or get_queryset should clean/expire it
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(reverse("isla-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # The reservation should now be cancelled automatically
        res.refresh_from_db()
        self.assertTrue(res.cancelada)

        # The island should be Disponible now
        self.isla1.refresh_from_db()
        self.assertEqual(self.isla1.estado, 'Disponible')

