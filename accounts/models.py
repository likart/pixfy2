from django.db import models
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Аватар")
    bio = models.TextField(max_length=500, blank=True, verbose_name="О себе")
    website = models.URLField(blank=True, verbose_name="Веб-сайт")
    location = models.CharField(max_length=100, blank=True, verbose_name="Местоположение")
    
    # Статистика
    total_photos = models.IntegerField(default=0, verbose_name="Всего фотографий")
    total_views = models.IntegerField(default=0, verbose_name="Всего просмотров")
    total_downloads = models.IntegerField(default=0, verbose_name="Всего загрузок")
    
    # Настройки
    email_notifications = models.BooleanField(default=True, verbose_name="Email уведомления")
    public_profile = models.BooleanField(default=True, verbose_name="Публичный профиль")
    is_contributor = models.BooleanField(default=False, verbose_name="Является автором")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return f"Профиль {self.user.username}"

    def update_stats(self):
        """Обновляет статистику пользователя"""
        from gallery.models import Photo
        stats = Photo.objects.filter(author=self.user).aggregate(
            total_photos=Count('id'),
            total_views=Sum('views'),
            total_downloads=Sum('downloads'),
        )
        self.total_photos = stats['total_photos'] or 0
        self.total_views = stats['total_views'] or 0
        self.total_downloads = stats['total_downloads'] or 0
        self.save()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Создает профиль пользователя при создании пользователя"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Сохраняет профиль пользователя при сохранении пользователя"""
    if hasattr(instance, 'profile'):
        instance.profile.save()
