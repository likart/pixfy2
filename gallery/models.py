import logging
import os
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS
import exifread
try:
    from iptcinfo3 import IPTCInfo
except ImportError:
    IPTCInfo = None


logger = logging.getLogger(__name__)


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название")
    slug = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Photo(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    keywords = models.CharField(max_length=500, verbose_name="Ключевые слова", help_text="Разделите запятыми")
    
    # Файлы
    image = models.ImageField(upload_to='photos/%Y/%m/', verbose_name="Изображение")
    thumbnail = models.ImageField(upload_to='thumbnails/%Y/%m/', blank=True, verbose_name="Превью")
    
    # Метаданные
    width = models.IntegerField(default=0, verbose_name="Ширина")
    height = models.IntegerField(default=0, verbose_name="Высота")
    file_size = models.IntegerField(default=0, verbose_name="Размер файла")
    format = models.CharField(max_length=10, blank=True, verbose_name="Формат")
    file_hash = models.CharField(max_length=64, blank=True, verbose_name="SHA256 хеш файла", db_index=True)
    base_price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('10.00'), verbose_name="Базовая цена, $")
    
    # Связи
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Автор")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Категория")
    
    # Даты
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    # Статистика
    views = models.IntegerField(default=0, verbose_name="Просмотры")
    downloads = models.IntegerField(default=0, verbose_name="Загрузки")
    
    # Статус
    is_approved = models.BooleanField(default=True, verbose_name="Одобрено")
    is_featured = models.BooleanField(default=False, verbose_name="Рекомендуемое")

    class Meta:
        verbose_name = "Фотография"
        verbose_name_plural = "Фотографии"
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Создаем превью при сохранении
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if self.image and not self.thumbnail:
            self.create_thumbnail()
            
        # Получаем метаданные изображения
        if self.image:
            self.get_image_metadata()
            
            # Извлекаем EXIF и IPTC данные только для новых фото
            if is_new:
                self.extract_metadata_from_file()
                
            super().save(update_fields=['width', 'height', 'file_size', 'format', 'thumbnail', 'title', 'description', 'keywords'])

    def create_thumbnail(self):
        """Создает превью изображения"""
        if not self.image:
            logger.debug("Thumbnail creation skipped: no image file.")
            return
            
        try:
            with Image.open(self.image.path) as img:
                img = ImageOps.exif_transpose(img)
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Создаем превью
                max_side = 960
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                
                # Сохраняем превью
                thumb_name = os.path.basename(self.image.name)
                thumb_name = os.path.splitext(thumb_name)[0] + '_thumb.jpg'
                timestamp = timezone.now()
                thumb_path = os.path.join(
                    'thumbnails',
                    str(timestamp.year),
                    f"{timestamp.month:02d}",
                    thumb_name,
                )

                buffer = BytesIO()
                img.save(buffer, 'JPEG', quality=70, optimize=True, subsampling=1)
                buffer.seek(0)
                self.thumbnail.save(thumb_path, ContentFile(buffer.read()), save=False)
        except Exception:
            logger.exception("Ошибка создания превью для %s", self.pk or self.image.name)

    def get_image_metadata(self):
        """Извлекает метаданные изображения"""
        if not self.image:
            return
            
        try:
            with Image.open(self.image.path) as img:
                self.width, self.height = img.size
                self.format = img.format
                self.file_size = os.path.getsize(self.image.path)
        except Exception as e:
            logger.warning("Ошибка получения метаданных изображения %s: %s", self.pk, e)

    def get_keywords_list(self):
        """Возвращает список ключевых слов"""
        return [k.strip() for k in self.keywords.split(',') if k.strip()]

    def increment_views(self):
        """Увеличивает счетчик просмотров"""
        self.views += 1
        self.save(update_fields=['views'])

    def increment_downloads(self):
        """Увеличивает счетчик загрузок"""
        self.downloads += 1
        self.save(update_fields=['downloads'])

    def extract_metadata_from_file(self):
        """Извлекает EXIF и IPTC метаданные из файла"""
        if not self.image:
            return
            
        try:
            logger.debug("Extracting metadata from %s", self.image.path)
            
            # Извлекаем EXIF данные
            exif_data = self.extract_exif_data()
            
            # Извлекаем IPTC данные
            iptc_data = self.extract_iptc_data()
            
            # Обновляем поля если данные найдены
            updated = False
            
            # Приоритет: IPTC > EXIF > текущие значения
            if iptc_data.get('title') and not self.title.strip():
                self.title = iptc_data['title'][:200]  # Ограничиваем длину
                updated = True
                
            if iptc_data.get('description') and not self.description.strip():
                self.description = iptc_data['description']
                updated = True
                
            if iptc_data.get('keywords'):
                if not self.keywords.strip():
                    self.keywords = ', '.join(iptc_data['keywords'])[:500]
                else:
                    # Добавляем к существующим ключевым словам
                    existing_keywords = [k.strip() for k in self.keywords.split(',') if k.strip()]
                    new_keywords = [k for k in iptc_data['keywords'] if k not in existing_keywords]
                    all_keywords = existing_keywords + new_keywords
                    self.keywords = ', '.join(all_keywords)[:500]
                updated = True
                
            # Если IPTC не дал результатов, пробуем EXIF
            if exif_data.get('title') and not self.title.strip():
                self.title = exif_data['title'][:200]
                updated = True
                
            if exif_data.get('description') and not self.description.strip():
                self.description = exif_data['description']
                updated = True
                
            if updated:
                logger.debug("Metadata updated for photo %s", self.pk)
                
        except Exception:
            logger.exception("Error extracting metadata for %s", self.pk)

    def decode_exif_string(self, value):
        """Декодирует EXIF строку из различных форматов"""
        if isinstance(value, (tuple, list)):
            # Если это массив байтов UTF-16
            try:
                # Конвертируем массив чисел в байты
                byte_array = bytes(value)
                # Декодируем как UTF-16 Little Endian
                decoded = byte_array.decode('utf-16le', errors='ignore')
                # Убираем нулевые символы
                decoded = decoded.replace('\x00', '').strip()
                return decoded
            except:
                pass
        
        if isinstance(value, bytes):
            try:
                # UTF-16 Little Endian (Windows XP tags)
                if value.startswith(b'\xff\xfe') or b'\x00' in value:
                    decoded = value.decode('utf-16le', errors='ignore').rstrip('\x00')
                    return decoded
            except:
                pass
                
            try:
                # UTF-8
                return value.decode('utf-8', errors='ignore')
            except:
                pass
                
            try:
                # ASCII
                return value.decode('ascii', errors='ignore')
            except:
                pass
        
        return str(value)

    def extract_exif_data(self):
        """Извлекает EXIF данные"""
        exif_data = {}
        
        try:
            with Image.open(self.image.path) as img:
                if hasattr(img, '_getexif'):
                    exif = img._getexif()
                    if exif:
                        for tag_id, value in exif.items():
                            tag = TAGS.get(tag_id, tag_id)
                            if tag == 'ImageDescription':
                                exif_data['description'] = self.decode_exif_string(value)
                            elif tag == 'XPTitle':
                                exif_data['title'] = self.decode_exif_string(value)
                            elif tag == 'XPKeywords':
                                keywords_str = self.decode_exif_string(value)
                                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                                if not keywords:
                                    keywords = [k.strip() for k in keywords_str.split(';') if k.strip()]
                                exif_data['keywords'] = keywords
                                
        except Exception as e:
            logger.debug("Error reading EXIF for %s: %s", self.pk, e)
            
        return exif_data

    def extract_iptc_data(self):
        """Извлекает IPTC данные"""
        iptc_data = {}
        
        if not IPTCInfo:
            return iptc_data
            
        try:
            info = IPTCInfo(self.image.path)
            
            # Используем правильные атрибуты для iptcinfo3
            try:
                # Заголовок/название
                if hasattr(info, 'headline') and info.headline:
                    iptc_data['title'] = info.headline
                elif hasattr(info, 'object_name') and info.object_name:
                    iptc_data['title'] = info.object_name
                    
                # Описание
                if hasattr(info, 'caption') and info.caption:
                    iptc_data['description'] = info.caption
                    
                # Ключевые слова
                if hasattr(info, 'keywords') and info.keywords:
                    if isinstance(info.keywords, list):
                        iptc_data['keywords'] = info.keywords
                    else:
                        iptc_data['keywords'] = [info.keywords]
                        
            except Exception as e:
                logger.debug("Error accessing IPTC properties for %s: %s", self.pk, e)
                    
        except Exception as e:
            logger.debug("Error reading IPTC for %s: %s", self.pk, e)
            
        return iptc_data


class PhotoView(models.Model):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Просмотр фотографии"
        verbose_name_plural = "Просмотры фотографий"
        unique_together = ['photo', 'ip_address', 'user']


class PhotoDownload(models.Model):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Загрузка фотографии"
        verbose_name_plural = "Загрузки фотографий"
