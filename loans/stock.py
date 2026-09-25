"""
Ajustes de stock de materiales causados por préstamos.
Deben llamarse dentro de transaction.atomic(): bloquean las filas de los materiales.
"""

from rest_framework.exceptions import ValidationError

from materials.models import Material


def adjust_materials_stock(deltas: dict[int, int]) -> None:
    """
    Suma a cada material su delta (negativo para descontar). Todo o nada: si a alguno le falta
    stock no se modifica ninguno. El stock nunca queda negativo.
    """
    deltas = {material_id: delta for material_id, delta in deltas.items() if delta}
    if not deltas:
        return
    # Bloqueo en orden de id para evitar interbloqueos entre peticiones concurrentes
    materials = list(Material.objects.select_for_update().filter(id__in=deltas).order_by('id'))

    for material in materials:
        if material.quantity + deltas[material.id] < 0:
            raise ValidationError(
                {"non_field_errors": [f"No hay suficiente stock de {material.name}. Disponible: {material.quantity}"]}
            )

    for material in materials:
        material.quantity += deltas[material.id]
        if material.quantity == 0 and material.status in ('Disponible', 'En préstamo'):
            material.status = 'No disponible'
        elif material.quantity > 0 and material.status == 'No disponible':
            material.status = 'Disponible'
        material.save(update_fields=['quantity', 'status', 'updated_at'])


def hold_items(items) -> None:
    """Descuenta del stock los renglones [(material_id, quantity)] de un préstamo."""
    adjust_materials_stock(_sum_by_material(items, sign=-1))


def release_loan_items(loan) -> None:
    """Devuelve al stock todos los renglones del préstamo."""
    adjust_materials_stock(
        _sum_by_material(((item.material_id, item.quantity) for item in loan.items.all()), sign=1)
    )


def _sum_by_material(items, sign):
    totals = {}
    for material_id, quantity in items:
        totals[material_id] = totals.get(material_id, 0) + sign * quantity
    return totals
