import os
import logging
from django.core.management.base import BaseCommand
from gallery.models import Photo

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Пересоздает все thumbnail изображения с новыми настройками размера и качества'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Пересоздать все thumbnails принудительно, даже если они уже существуют',
        )

    def handle(self, *args, **options):
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('Запуск пересоздания thumbnail изображений')
        )
        
        photos = Photo.objects.all()
        total_photos = photos.count()
        processed = 0
        errors = 0
        
        self.stdout.write(f'Найдено {total_photos} фотографий для обработки')
        
        for photo in photos:
            try:
                # Проверяем нужно ли пересоздавать thumbnail
                recreate = force or not photo.thumbnail or not os.path.exists(photo.thumbnail.path) if photo.thumbnail else True
                
                if recreate:
                    # Удаляем старый thumbnail если есть (включая старые JPEG)
                    if photo.thumbnail and os.path.exists(photo.thumbnail.path):
                        try:
                            os.remove(photo.thumbnail.path)
                        except OSError:
                            pass
                    
                    # Также удаляем старые JPEG thumbnail если они есть
                    old_jpg_thumb = photo.thumbnail.path.replace('.webp', '.jpg') if photo.thumbnail else None
                    if old_jpg_thumb and os.path.exists(old_jpg_thumb):
                        try:
                            os.remove(old_jpg_thumb)
                        except OSError:
                            pass
                    
                    # Создаем новый thumbnail
                    photo.create_thumbnail()
                    processed += 1
                    
                    if processed % 10 == 0:
                        self.stdout.write(f'Обработано {processed} из {total_photos}...')
                else:
                    self.stdout.write(f'Пропускаем фото ID {photo.id} - thumbnail уже существует')
                    
            except Exception as e:
                logger.exception(f"Ошибка обработки фото ID {photo.id}: {e}")
                errors += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Готово! Обработано: {processed}, Ошибок: {errors}')
        )
