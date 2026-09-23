from django.contrib import admin

from .models import Carrera, UserProfile


@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')
    search_fields = ('nombre',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('matricula', 'user', 'carrera')
    search_fields = ('matricula', 'user__username', 'user__email')
    list_filter = ('carrera',)
