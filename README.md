# SIDERED — Backend

API en Django + DRF para la gestión del laboratorio de redes.

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate        # fish: source .venv/bin/activate.fish
pip install -r requirements.txt

cp .env.example .env             # ajusta credenciales de BD y correo
createdb bdinventario_redes      # o: CREATE DATABASE bdinventario_redes;

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Documentación (Swagger): http://localhost:8000/api/docs/
- Token JWT: `POST /api/token/` con `{"username", "password"}`

## Tests

```bash
python manage.py test
```

## Correo

Configúralo en `.env` (ver `.env.example`):

- **Desarrollo:** `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` imprime los correos en la consola.
- **Gmail:** activa la verificación en dos pasos, genera una contraseña de aplicación y colócala en
  `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`.

`FRONTEND_URL` (por defecto `http://localhost:3000`) se usa para los enlaces de los correos.

## Recordatorios de entrega

El command `enviar_recordatorios` avisa por correo a los alumnos que no han entregado:
24 h antes, 1 h antes y una vez al vencer (solo actividades vencidas hace 7 días o menos).
Es idempotente: cada aviso se envía una sola vez por alumno y actividad.

```bash
python manage.py enviar_recordatorios            # envía
python manage.py enviar_recordatorios --dry-run  # solo muestra a quién se enviaría
```

Programarlo cada 15 minutos con cron (`crontab -e`):

```
*/15 * * * * cd /ruta/a/back_inventario && .venv/bin/python manage.py enviar_recordatorios >> /tmp/sidered-recordatorios.log 2>&1
```

O con un timer de systemd (usuario):

```ini
# ~/.config/systemd/user/sidered-recordatorios.service
[Unit]
Description=SIDERED recordatorios de entrega

[Service]
Type=oneshot
WorkingDirectory=/ruta/a/back_inventario
ExecStart=/ruta/a/back_inventario/.venv/bin/python manage.py enviar_recordatorios

# ~/.config/systemd/user/sidered-recordatorios.timer
[Unit]
Description=Ejecuta los recordatorios de SIDERED cada 15 minutos

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now sidered-recordatorios.timer
```

Los correos por cambio de estado de una entrega ("En revisión" y "Calificado") se envían
automáticamente al actualizarla; no requieren el command.

## Sesiones (JWT)

- `POST /api/token/` devuelve `access` (60 min) y `refresh` (1 día). Límite: 10 intentos por minuto por usuario y 60 por IP.
- `POST /api/token/refresh/` devuelve un `access` **y un `refresh` nuevos**; el refresh usado queda invalidado.
- `POST /api/logout/` con `{"refresh": "..."}` invalida la sesión.
- Restablecer la contraseña cierra todas las sesiones de la cuenta.

Limpia periódicamente los tokens vencidos (por ejemplo, una vez al día):

```bash
python manage.py flushexpiredtokens
```
