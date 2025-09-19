from django.contrib import admin

from .models import LicenseType, Order, OrderItem


@admin.register(LicenseType)
class LicenseTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_multiplier', 'is_active', 'sort_order')
    list_editable = ('price_multiplier', 'is_active', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('photo', 'license_type', 'unit_price', 'quantity', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__username', 'email', 'payment_reference')
    readonly_fields = ('created_at', 'updated_at', 'total_amount')
    inlines = [OrderItemInline]
