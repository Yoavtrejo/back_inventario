from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('kind', 'user', 'activity', 'sent_at')
    list_filter = ('kind',)
    search_fields = ('user__username', 'user__email', 'activity__title')
