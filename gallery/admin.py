from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Photo, PhotoView, PhotoDownload


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'category', 'base_price', 'is_approved', 'is_featured', 'views', 'downloads', 'uploaded_at']
    list_filter = ['is_approved', 'is_featured', 'category', 'uploaded_at', 'author']
    search_fields = ['title', 'keywords', 'description']
    readonly_fields = ['width', 'height', 'file_size', 'format', 'views', 'downloads', 'uploaded_at', 'updated_at', 'thumbnail_preview']
    list_editable = ['is_approved', 'is_featured']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'keywords', 'category', 'author')
        }),
        ('Файлы', {
            'fields': ('image', 'thumbnail', 'thumbnail_preview')
        }),
        ('Метаданные', {
            'fields': ('width', 'height', 'file_size', 'format', 'base_price'),
            'classes': ('collapse',)
        }),
        ('Статус', {
            'fields': ('is_approved', 'is_featured')
        }),
        ('Статистика', {
            'fields': ('views', 'downloads', 'uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html('<img src="{}" width="150" height="150" style="object-fit: cover;" />', obj.thumbnail.url)
        return "Нет превью"
    thumbnail_preview.short_description = "Превью"

    def save_model(self, request, obj, form, change):
        if not change:  # Если это новый объект
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(PhotoView)
class PhotoViewAdmin(admin.ModelAdmin):
    list_display = ['photo', 'user', 'ip_address', 'viewed_at']
    list_filter = ['viewed_at']
    readonly_fields = ['photo', 'user', 'ip_address', 'viewed_at']


@admin.register(PhotoDownload)
class PhotoDownloadAdmin(admin.ModelAdmin):
    list_display = ['photo', 'user', 'ip_address', 'downloaded_at']
    list_filter = ['downloaded_at']
    readonly_fields = ['photo', 'user', 'ip_address', 'downloaded_at']
