"""
Ajustes de stock de materiales causados por préstamos.
Deben llamarse dentro de transaction.atomic(): bloquean la fila del material.
"""

from rest_framework.exceptions import ValidationError

from materials.models import Material


def adjust_material_stock(material_id: int, delta: int) -> Material:
    """Suma ``delta`` al stock del material (negativo para descontar). El stock nunca queda negativo."""
    material = Material.objects.select_for_update().get(pk=material_id)
    new_quantity = material.quantity + delta
    if new_quantity < 0:
        raise ValidationError({"quantity": f"No hay suficiente stock. Disponible: {material.quantity}"})

    material.quantity = new_quantity
    if new_quantity == 0 and material.status in ('Disponible', 'En préstamo'):
        material.status = 'No disponible'
    elif new_quantity > 0 and material.status == 'No disponible':
        material.status = 'Disponible'
    material.save(update_fields=['quantity', 'status', 'updated_at'])
    return material
