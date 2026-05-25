"""
Django admin registration for loans.
"""

from __future__ import annotations

from django.contrib import admin

from .models import MaterialLoan


@admin.register(MaterialLoan)
class MaterialLoanAdmin(admin.ModelAdmin):
    """Admin list/detail for material loans."""

    list_display = (
        "id",
        "material",
        "quantity",
        "loan_period_days",
        "loan_date",
        "return_date",
        "requested_by",
        "approved_by",
        "created_at",
    )
    list_select_related = ("requested_by", "approved_by", "material")
    search_fields = ("material__name", "requested_by__username", "approved_by__username")
    readonly_fields = ("created_at", "updated_at")
