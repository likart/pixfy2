from decimal import Decimal

from django.conf import settings
from django.db import models

from gallery.models import Photo


class LicenseType(models.Model):
    name = models.CharField(max_length=120, verbose_name="Название лицензии")
    slug = models.SlugField(max_length=60, unique=True)
    short_description = models.CharField(max_length=255, verbose_name="Короткое описание")
    description = models.TextField(blank=True, verbose_name="Полные условия")
    price_multiplier = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.00'), verbose_name="Множитель цены")
    allowed_usage = models.TextField(blank=True, verbose_name="Разрешённое использование")
    assets_limit = models.CharField(max_length=120, blank=True, verbose_name="Ограничения по тиражу")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = "Тип лицензии"
        verbose_name_plural = "Типы лицензий"

    def __str__(self) -> str:
        return self.name

    def get_price_for_photo(self, photo: Photo) -> Decimal:
        base = photo.base_price or Decimal('0.00')
        return (base * self.price_multiplier).quantize(Decimal('0.01'))


class Order(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_AWAITING_PAYMENT = 'awaiting_payment'
    STATUS_PAID = 'paid'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Черновик'),
        (STATUS_AWAITING_PAYMENT, 'Ожидает оплаты'),
        (STATUS_PAID, 'Оплачен'),
        (STATUS_COMPLETED, 'Завершён'),
        (STATUS_CANCELLED, 'Отменён'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders', verbose_name="Клиент")
    full_name = models.CharField(max_length=150, verbose_name="Имя и фамилия")
    email = models.EmailField(verbose_name="Email")
    company = models.CharField(max_length=150, blank=True, verbose_name="Компания")
    notes = models.TextField(blank=True, verbose_name="Комментарий")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AWAITING_PAYMENT, verbose_name="Статус")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Сумма")
    payment_reference = models.CharField(max_length=120, blank=True, verbose_name="Номер платежа")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self) -> str:
        return f"Заказ #{self.id}"

    def recalc_totals(self):
        total = sum((item.total_price for item in self.items.all()), Decimal('0.00'))
        self.total_amount = total.quantize(Decimal('0.01'))
        self.save(update_fields=['total_amount', 'updated_at'])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name="Заказ")
    photo = models.ForeignKey(Photo, on_delete=models.PROTECT, related_name='order_items', verbose_name="Фотография")
    license_type = models.ForeignKey(LicenseType, on_delete=models.PROTECT, related_name='order_items', verbose_name="Лицензия")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"

    def __str__(self) -> str:
        return f"{self.photo.title} ({self.license_type.name})"

    @property
    def total_price(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal('0.01'))
