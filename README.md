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
