from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль'
    readonly_fields = ['total_photos', 'total_views', 'total_downloads', 'created_at', 'updated_at', 'avatar_preview']
    
    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover; border-radius: 50%;" />', obj.avatar.url)
        return "Нет аватара"
    avatar_preview.short_description = "Превью аватара"


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'location', 'total_photos', 'total_views', 'total_downloads', 'public_profile']
    list_filter = ['public_profile', 'email_notifications', 'created_at']
    search_fields = ['user__username', 'user__email', 'location']
    readonly_fields = ['total_photos', 'total_views', 'total_downloads', 'created_at', 'updated_at', 'avatar_preview']
    
    fieldsets = (
        ('Пользователь', {
            'fields': ('user',)
        }),
        ('Профиль', {
            'fields': ('avatar', 'avatar_preview', 'bio', 'website', 'location')
        }),
        ('Статистика', {
            'fields': ('total_photos', 'total_views', 'total_downloads'),
            'classes': ('collapse',)
        }),
        ('Настройки', {
            'fields': ('email_notifications', 'public_profile')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover; border-radius: 50%;" />', obj.avatar.url)
        return "Нет аватара"
    avatar_preview.short_description = "Превью аватара"


# Перерегистрируем UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)