"""
Inscripción automática por grupo escolar (cohorte = carrera + cuatrimestre + grupo).

Cada alumno queda inscrito en todos los ClassGroup de su cohorte del cuatrimestre activo.
Todas las operaciones son idempotentes (students.add no duplica) y no tocan las inscripciones
manuales a grupos de otra cohorte.
"""

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import ClassGroup, Term


def active_term():
    return Term.objects.filter(is_active=True).first()


def cohort_groups(cohort, term=None):
    """ClassGroup del term (por defecto el activo) con esa carrera, cuatrimestre y grupo."""
    term = term or active_term()
    if not cohort or term is None:
        return ClassGroup.objects.none()
    carrera_id, cuatrimestre, grupo = cohort
    return ClassGroup.objects.filter(term=term, carrera_id=carrera_id, cuatrimestre=cuatrimestre, grupo=grupo)


def group_cohort(group):
    if group.carrera_id and group.cuatrimestre and group.grupo:
        return (group.carrera_id, group.cuatrimestre, group.grupo)
    return None


def cohort_students(cohort):
    """Alumnos (ni staff ni admin) cuyo perfil pertenece a la cohorte."""
    if not cohort:
        return get_user_model().objects.none()
    carrera_id, cuatrimestre, grupo = cohort
    return get_user_model().objects.filter(
        is_staff=False, is_superuser=False,
        profile__carrera_id=carrera_id, profile__cuatrimestre=cuatrimestre, profile__grupo=grupo,
    )


def user_cohort(user):
    profile = getattr(user, 'profile', None)
    return profile.cohorte if profile else None


@transaction.atomic
def enroll_student(user):
    """Registro o perfil completado: inscribe al alumno en los grupos de su cohorte."""
    if user.is_staff or user.is_superuser:
        return
    for group in cohort_groups(user_cohort(user)):
        group.students.add(user)


@transaction.atomic
def move_student(user, old_cohort, new_cohort):
    """El admin cambió la cohorte: sale solo de los grupos de la anterior y entra a los de la nueva."""
    if old_cohort == new_cohort:
        return
    for group in cohort_groups(old_cohort):
        group.students.remove(user)
    enroll_student(user)


@transaction.atomic
def enroll_group_cohort(group):
    """Grupo con cohorte en el term activo: inscribe a todos los alumnos de esa cohorte."""
    cohort = group_cohort(group)
    if not cohort or not Term.objects.filter(pk=group.term_id, is_active=True).exists():
        return
    group.students.add(*cohort_students(cohort))


@transaction.atomic
def enroll_term(term):
    """El term se activó: inscribe por cohortes en todos sus grupos."""
    for group in ClassGroup.objects.filter(term=term, carrera__isnull=False, cuatrimestre__isnull=False,
                                           grupo__isnull=False):
        group.students.add(*cohort_students(group_cohort(group)))
