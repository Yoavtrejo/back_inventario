from datetime import datetime, date, time, timedelta
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Isla, Reservacion

User = get_user_model()


class AlumnoCompactSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')


class IslaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Isla
        fields = (
            'id', 'numero_isla', 'equipos_computo', 'switches', 
            'routers', 'otros_componentes', 'qr_token', 'estado', 
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'qr_token', 'created_at', 'updated_at')


class ReservacionSerializer(serializers.ModelSerializer):
    alumno = AlumnoCompactSerializer(read_only=True)
    isla_detalles = IslaSerializer(source='isla', read_only=True)

    class Meta:
        model = Reservacion
        fields = (
            'id', 'isla', 'isla_detalles', 'alumno', 'fecha_reserva', 
            'hora_inicio', 'duracion_horas', 'hora_escaneo_inicio', 
            'completada', 'cancelada', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'alumno', 'hora_escaneo_inicio', 
            'completada', 'cancelada', 'created_at', 'updated_at'
        )

    def validate(self, attrs):
        isla = attrs.get('isla')
        fecha_reserva = attrs.get('fecha_reserva')
        hora_inicio = attrs.get('hora_inicio')
        duracion_horas = attrs.get('duracion_horas', 1)

        # Si estamos actualizando, recuperamos los valores existentes para validar
        if self.instance:
            isla = isla or self.instance.isla
            fecha_reserva = fecha_reserva or self.instance.fecha_reserva
            hora_inicio = hora_inicio or self.instance.hora_inicio
            duracion_horas = duracion_horas if 'duracion_horas' in attrs else self.instance.duracion_horas

        # Validar duración máxima de 4 horas
        if duracion_horas > 4:
            raise serializers.ValidationError(
                {"duracion_horas": "La duración máxima permitida es de 4 horas."}
            )
        if duracion_horas < 1:
            raise serializers.ValidationError(
                {"duracion_horas": "La duración mínima permitida es de 1 hora."}
            )

        # Validar fecha no sea en el pasado
        if fecha_reserva < date.today():
            raise serializers.ValidationError(
                {"fecha_reserva": "No se pueden realizar reservaciones en fechas pasadas."}
            )

        # Validar solapamiento de horarios para la misma isla
        start_datetime = datetime.combine(fecha_reserva, hora_inicio)
        end_datetime = start_datetime + timedelta(hours=duracion_horas)

        # Buscar reservaciones activas (no completadas, no canceladas) para el mismo día y la misma isla
        existing_reservations = Reservacion.objects.filter(
            isla=isla,
            fecha_reserva=fecha_reserva,
            completada=False,
            cancelada=False
        )

        if self.instance:
            existing_reservations = existing_reservations.exclude(id=self.instance.id)

        for res in existing_reservations:
            res_start = datetime.combine(res.fecha_reserva, res.hora_inicio)
            res_end = res_start + timedelta(hours=res.duracion_horas)

            # Verificar solapamiento: (StartA < EndB) y (EndA > StartB)
            if start_datetime < res_end and end_datetime > res_start:
                raise serializers.ValidationError(
                    "Esta isla ya se encuentra reservada en el horario solicitado (de {} a {}).".format(
                        res_start.strftime("%H:%M"),
                        res_end.strftime("%H:%M")
                    )
                )

        return attrs
