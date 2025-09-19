import os
import time
import json
import logging
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone

from gallery.models import Photo, Category
from gallery.views import is_valid_image_file, calculate_file_hash, extract_file_metadata

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Обрабатывает файлы из временных папок пользователей каждые 5 секунд'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Интервал проверки в секундах (по умолчанию 5)',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Выполнить только одну итерацию обработки',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        run_once = options['once']
        
        self.stdout.write(
            self.style.SUCCESS(f'Запуск обработки временных файлов с интервалом {interval} секунд')
        )
        
        try:
            while True:
                self.process_all_temp_files()
                
                if run_once:
                    break
                    
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nОстановка обработки по Ctrl+C'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Критическая ошибка: {e}'))
            logger.exception("Критическая ошибка в process_temp_files")

    def process_all_temp_files(self):
        """Обрабатывает файлы из всех временных папок пользователей"""
        temp_base = os.path.join(settings.MEDIA_ROOT, 'temp', 'users')
        
        if not os.path.exists(temp_base):
            return
        
        processed_count = 0
        
        # Проходим по всем папкам пользователей
        for user_folder_name in os.listdir(temp_base):
            user_folder_path = os.path.join(temp_base, user_folder_name)
            
            if not os.path.isdir(user_folder_path):
                continue
                
            try:
                user_id = int(user_folder_name)
                user = User.objects.get(id=user_id)
                
                files_processed = self.process_user_temp_files(user, user_folder_path)
                processed_count += files_processed
                
            except (ValueError, User.DoesNotExist) as e:
                logger.warning(f"Пропуск папки {user_folder_name}: {e}")
                continue
        
        if processed_count > 0:
            self.stdout.write(f'Обработано файлов: {processed_count}')

    def process_user_temp_files(self, user, user_folder_path):
        """Обрабатывает файлы конкретного пользователя"""
        if not os.path.exists(user_folder_path):
            return 0
        
        processed_count = 0
        
        # Получаем все файлы в папке
        for filename in os.listdir(user_folder_path):
            file_path = os.path.join(user_folder_path, filename)
            
            if not os.path.isfile(file_path):
                continue
                
            try:
                success = self.process_single_file(user, file_path, filename)
                if success:
                    processed_count += 1
                    
            except Exception as e:
                logger.exception(f"Ошибка обработки файла {file_path}: {e}")
                # В случае ошибки удаляем проблемный файл
                try:
                    os.remove(file_path)
                except:
                    pass
        
        return processed_count

    def process_single_file(self, user, file_path, filename):
        """Обрабатывает один файл"""
        logger.info(f"Обработка файла {filename} пользователя {user.username}")
        
        # Шаг 1: Проверка целостности и типа файла
        is_valid, error_message = is_valid_image_file(file_path)
        if not is_valid:
            logger.warning(f"Файл {filename} не прошел валидацию: {error_message}")
            os.remove(file_path)
            return False
        
        # Шаг 2: Проверка на дубликаты по хешу
        file_hash = calculate_file_hash(file_path)
        if file_hash:
            existing_photo = Photo.objects.filter(
                file_hash=file_hash  # Нужно добавить это поле в модель
            ).first()
            
            if existing_photo:
                logger.info(f"Файл {filename} уже существует в базе (дубликат, ID: {existing_photo.id})")
                os.remove(file_path)
                return False
        
        # Шаг 3: Извлечение метаданных с помощью ExifTool
        metadata = extract_file_metadata(file_path)
        
        # Шаг 4: Создание записи в базе данных
        try:
            # Генерируем название по умолчанию из имени файла
            original_name = os.path.splitext(filename)[0]
            # Убираем timestamp префикс если есть
            if '_' in original_name and original_name.split('_')[0].isdigit():
                title = '_'.join(original_name.split('_')[1:])
            else:
                title = original_name
            
            # Используем метаданные если доступны
            if metadata.get('title'):
                title = metadata['title']
            
            # Создаем фото объект
            photo = Photo(
                title=title,
                description=metadata.get('description', ''),
                keywords=', '.join(metadata.get('keywords', [])),
                author=user,
                file_hash=file_hash,
                is_approved=True  # Автоматически одобряем
            )
            
            # Шаг 5: Перемещение файла в постоянное хранилище
            # Генерируем путь для сохранения
            now = timezone.now()
            relative_path = f"photos/{now.year}/{now.month:02d}/{filename}"
            full_destination_path = os.path.join(settings.MEDIA_ROOT, relative_path)
            
            # Создаем папку если не существует
            os.makedirs(os.path.dirname(full_destination_path), exist_ok=True)
            
            # Перемещаем файл
            shutil.move(file_path, full_destination_path)
            
            # Устанавливаем путь в модели
            photo.image.name = relative_path
            
            # Сохраняем в базу данных
            photo.save()
            
            logger.info(f"Файл {filename} успешно обработан и добавлен как Photo ID {photo.id}")
            return True
            
        except Exception as e:
            logger.exception(f"Ошибка создания Photo для файла {filename}: {e}")
            # Удаляем файл в случае ошибки
            try:
                os.remove(file_path)
            except:
                pass
            return False
