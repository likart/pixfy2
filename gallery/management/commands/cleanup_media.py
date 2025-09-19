import os
import logging
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db.models import Q

from gallery.models import Photo

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Очищает файлы-сироты и пустые папки в media директории'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет удалено без фактического удаления',
        )
        parser.add_argument(
            '--remove-empty-dirs',
            action='store_true',
            help='Удалить пустые директории',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        remove_empty_dirs = options['remove_empty_dirs']
        
        self.stdout.write(
            self.style.SUCCESS('Запуск очистки файлов-сирот в media папке')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Режим DRY-RUN: файлы не будут удалены'))
        
        try:
            orphan_files = self.find_orphan_files()
            self.cleanup_orphan_files(orphan_files, dry_run)
            
            if remove_empty_dirs:
                self.cleanup_empty_dirs(dry_run)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Критическая ошибка: {e}'))
            logger.exception("Критическая ошибка в cleanup_media")

    def find_orphan_files(self):
        """Находит файлы-сироты (файлы на диске без записей в БД)"""
        orphan_files = []
        
        # Получаем все пути файлов из базы данных
        db_image_paths = set(Photo.objects.exclude(
            Q(image='') | Q(image__isnull=True)
        ).values_list('image', flat=True))
        
        db_thumbnail_paths = set(Photo.objects.exclude(
            Q(thumbnail='') | Q(thumbnail__isnull=True)
        ).values_list('thumbnail', flat=True))
        
        # Объединяем все пути из БД
        db_paths = db_image_paths.union(db_thumbnail_paths)
        db_full_paths = {os.path.join(settings.MEDIA_ROOT, path) for path in db_paths}
        
        # Сканируем директории с файлами
        media_dirs = [
            os.path.join(settings.MEDIA_ROOT, 'photos'),
            os.path.join(settings.MEDIA_ROOT, 'thumbnails')
        ]
        
        for media_dir in media_dirs:
            if not os.path.exists(media_dir):
                continue
                
            for root, dirs, files in os.walk(media_dir):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                        file_path = os.path.join(root, file)
                        
                        # Если файла нет в базе данных - это сирота
                        if file_path not in db_full_paths:
                            orphan_files.append(file_path)
        
        return orphan_files

    def cleanup_orphan_files(self, orphan_files, dry_run):
        """Удаляет файлы-сироты"""
        if not orphan_files:
            self.stdout.write(self.style.SUCCESS('Файлы-сироты не найдены'))
            return
        
        self.stdout.write(f'Найдено файлов-сирот: {len(orphan_files)}')
        
        for file_path in orphan_files:
            rel_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
            
            if dry_run:
                self.stdout.write(f'[DRY-RUN] Удалился бы файл: {rel_path}')
            else:
                try:
                    os.remove(file_path)
                    self.stdout.write(f'Удален файл-сирота: {rel_path}')
                except OSError as e:
                    self.stdout.write(
                        self.style.ERROR(f'Ошибка удаления {rel_path}: {e}')
                    )

    def cleanup_empty_dirs(self, dry_run):
        """Удаляет пустые директории"""
        media_dirs = [
            os.path.join(settings.MEDIA_ROOT, 'photos'),
            os.path.join(settings.MEDIA_ROOT, 'thumbnails')
        ]
        
        for media_dir in media_dirs:
            if not os.path.exists(media_dir):
                continue
                
            # Идем от самых глубоких папок к корневым
            for root, dirs, files in os.walk(media_dir, topdown=False):
                if not dirs and not files:  # Пустая папка
                    rel_path = os.path.relpath(root, settings.MEDIA_ROOT)
                    
                    if dry_run:
                        self.stdout.write(f'[DRY-RUN] Удалилась бы пустая папка: {rel_path}')
                    else:
                        try:
                            os.rmdir(root)
                            self.stdout.write(f'Удалена пустая папка: {rel_path}')
                        except OSError as e:
                            # Ignore errors (папка может быть не пустой из-за скрытых файлов)
                            pass
