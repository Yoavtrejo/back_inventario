from django.contrib import admin

from .models import Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'created_by', 'created_at')
    search_fields = ('title', 'description')
