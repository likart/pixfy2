import logging
import os
import re
import json
import time
import hashlib
from pathlib import Path

from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from PIL import Image
import exifread
import subprocess
from rest_framework.decorators import api_view
from rest_framework.response import Response
try:
    from iptcinfo3 import IPTCInfo
except ImportError:
    IPTCInfo = None

from store.models import LicenseType
from store.services import user_has_active_license

from .models import Photo, Category, PhotoView, PhotoDownload


logger = logging.getLogger(__name__)


def get_user_temp_folder(user):
    """Получает путь к временной папке пользователя"""
    temp_base = os.path.join(settings.MEDIA_ROOT, 'temp', 'users')
    user_folder = os.path.join(temp_base, str(user.id))
    
    # Создаем папку если её нет
    os.makedirs(user_folder, exist_ok=True)
    
    return user_folder


def is_valid_image_file(file_path):
    """Проверяет, является ли файл валидным изображением JPG"""
    try:
        # Проверяем существование файла
        if not os.path.exists(file_path):
            return False, "Файл не существует"
            
        # Проверяем размер файла
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, "Файл пустой"
        if file_size > 50 * 1024 * 1024:  # 50MB
            return False, "Файл слишком большой"
            
        # Проверяем, что это изображение с помощью PIL
        with Image.open(file_path) as img:
            # Проверяем формат
            if img.format not in ['JPEG', 'JPG']:
                return False, "Файл должен быть в формате JPG"
                
            # Проверяем размеры
            width, height = img.size
            if width < 100 or height < 100:
                return False, "Изображение слишком маленькое (мин. 100x100)"
            if width > 10000 or height > 10000:
                return False, "Изображение слишком большое (макс. 10000x10000)"
                
        return True, "OK"
        
    except Exception as e:
        return False, f"Ошибка проверки файла: {str(e)}"


def calculate_file_hash(file_path):
    """Вычисляет SHA256 хеш файла"""
    hash_sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.error("Ошибка вычисления хеша файла %s: %s", file_path, e)
        return None


def apply_smart_sorting(queryset):
    """
    Применяет умную сортировку к queryset фотографий:
    1. Приоритет скачиваний (downloads) - главный критерий
    2. Затем просмотры (views) - второй критерий  
    3. Рандом среди равных - если скачивания и просмотры одинаковые
    """
    from django.db.models import Case, When, IntegerField, F
    from django.db.models.functions import Random
    
    return queryset.annotate(
        # Создаем приоритетный балл: downloads * 10 + views
        priority_score=Case(
            When(downloads__gt=0, then=F('downloads') * 10 + F('views')),
            When(views__gt=0, then=F('views')),
            default=0,
            output_field=IntegerField()
        ),
        # Добавляем случайное число для рандомизации среди равных
        random_order=Random()
    ).order_by('-priority_score', '-downloads', '-views', 'random_order')


def apply_search_filters(queryset, search_query):
    """Применяет фильтры поиска по целым словам"""
    if not search_query:
        return queryset

    search_words = [word.strip() for word in search_query.split() if word.strip()]
    for word in search_words:
        word_pattern = r'\b' + re.escape(word) + r'\b'
        queryset = queryset.filter(
            Q(title__iregex=word_pattern) |
            Q(keywords__iregex=word_pattern) |
            Q(description__iregex=word_pattern)
        )
    return queryset


def home(request):
    """Главная страница с галереей фотографий"""
    search_query = request.GET.get('search', '')
    category_slug = request.GET.get('category', '')

    photos = (
        Photo.objects.filter(is_approved=True)
        .select_related('category', 'author', 'author__profile')
    )

    photos = apply_search_filters(photos, search_query)

    if category_slug:
        photos = photos.filter(category__slug=category_slug)

    photos = apply_smart_sorting(photos)

    paginator = Paginator(photos, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.all()

    context = {
        'photos': page_obj,
        'categories': categories,
        'search_query': search_query,
        'current_category': category_slug,
        'total_photos': paginator.count,
    }

    return render(request, 'gallery/home.html', context)


def photo_detail(request, photo_id):
    """Детальная страница фотографии"""
    photo = get_object_or_404(Photo, id=photo_id, is_approved=True)
    
    # Записываем просмотр
    ip_address = get_client_ip(request)
    view, created = PhotoView.objects.get_or_create(
        photo=photo,
        ip_address=ip_address,
        user=request.user if request.user.is_authenticated else None
    )
    
    if created:
        photo.increment_views()
    
    # Похожие фотографии
    related_photos = Photo.objects.filter(
        is_approved=True,
        category=photo.category
    ).exclude(id=photo.id)[:8]

    license_types = LicenseType.objects.filter(is_active=True).order_by('sort_order', 'id')
    license_options = [
        {
            'license': license,
            'price': license.get_price_for_photo(photo),
        }
        for license in license_types
    ]
    if request.user.is_authenticated and getattr(getattr(request.user, 'profile', None), 'is_contributor', False):
        license_options = []
    can_download = False
    if request.user.is_authenticated:
        if request.user == photo.author:
            can_download = True
        elif user_has_active_license(request.user, photo):
            can_download = True
    
    context = {
        'photo': photo,
        'related_photos': related_photos,
        'keywords': photo.get_keywords_list(),
        'license_options': license_options,
        'can_download': can_download,
    }

    return render(request, 'gallery/photo_detail.html', context)


@login_required
def upload_photo(request):
    """Страница загрузки фотографий"""
    if not getattr(getattr(request.user, 'profile', None), 'is_contributor', False):
        messages.error(request, 'Загрузка доступна только авторам. Используйте авторский аккаунт.')
        return redirect('gallery:home')
    
    return render(request, 'gallery/upload.html')


@login_required
@require_http_methods(["POST"])
def upload_to_temp(request):
    """Загрузка файла во временную папку пользователя"""
    try:
        logger.info(
            "Temp upload request user=%s authenticated=%s is_contributor=%s files=%s",
            getattr(request.user, 'username', None),
            request.user.is_authenticated,
            getattr(getattr(request.user, 'profile', None), 'is_contributor', False),
            list(request.FILES.keys()),
        )

        # Проверяем права пользователя
        if not getattr(getattr(request.user, 'profile', None), 'is_contributor', False):
            return JsonResponse({'error': 'Загрузка доступна только авторам PixFy.'}, status=403)

        if 'file' not in request.FILES:
            return JsonResponse({'error': 'Файл не выбран'}, status=400)
        
        file = request.FILES['file']
        
        logger.debug(
            "Processing temp file name=%s size=%s type=%s",
            file.name,
            file.size,
            file.content_type,
        )
        
        # Базовая валидация файла
        if not file.content_type.startswith('image/'):
            return JsonResponse({'error': 'Файл должен быть изображением'}, status=400)
            
        if not re.match(r'^image\/(jpeg|jpg)$', file.content_type):
            return JsonResponse({'error': 'Поддерживаются только JPG файлы'}, status=400)
        
        if file.size > 50 * 1024 * 1024:  # 50MB
            return JsonResponse({'error': 'Файл слишком большой (макс. 50 МБ)'}, status=400)
        
        # Получаем временную папку пользователя
        temp_folder = get_user_temp_folder(request.user)
        
        # Генерируем уникальное имя файла
        timestamp = int(time.time() * 1000)  # миллисекунды
        file_extension = os.path.splitext(file.name)[1].lower()
        temp_filename = f"{timestamp}_{file.name}"
        temp_filepath = os.path.join(temp_folder, temp_filename)
        
        # Сохраняем файл во временную папку
        with open(temp_filepath, 'wb') as temp_file:
            for chunk in file.chunks():
                temp_file.write(chunk)
        
        logger.info("File saved to temp folder: %s", temp_filepath)
        
        return JsonResponse({
            'success': True,
            'message': 'Файл загружен во временную папку',
            'filename': temp_filename,
            'size': file.size
        })

    except Exception as e:
        logger.exception("Ошибка загрузки файла во временную папку")
        return JsonResponse({'error': f'Ошибка сервера: {str(e)}'}, status=500)


@require_http_methods(["POST"])
def handle_photo_upload(request):
    """Обработка загрузки фотографии через AJAX"""
    try:
        logger.debug(
            "Upload request user=%s authenticated=%s files=%s post=%s",
            getattr(request.user, 'username', None),
            request.user.is_authenticated,
            list(request.FILES.keys()),
            dict(request.POST),
        )

        # Проверяем аутентификацию
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Необходимо войти в систему'}, status=401)

        if not getattr(getattr(request.user, 'profile', None), 'is_contributor', False):
            return JsonResponse({'error': 'Загрузка доступна только авторам PixFy.'}, status=403)

        if 'file' not in request.FILES:
            return JsonResponse({'error': 'Файл не выбран'}, status=400)
        
        file = request.FILES['file']
        title = request.POST.get('title', file.name)
        description = request.POST.get('description', '')
        keywords = request.POST.get('keywords', '')
        category_id = request.POST.get('category')
        
        logger.debug(
            "Processing file name=%s size=%s type=%s",
            file.name,
            file.size,
            file.content_type,
        )
        
        # Валидация файла
        if not file.content_type.startswith('image/'):
            return JsonResponse({'error': 'Файл должен быть изображением'}, status=400)
        
        # Создаем фотографию
        default_title = re.sub(r'\.[^.]+$', '', file.name) if not title.strip() else title
        
        photo = Photo(
            title=default_title,
            description=description,
            keywords=keywords,
            author=request.user,
            image=file
        )
        
        if category_id:
            try:
                photo.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                pass
        
        photo.save()
        
        # Извлекаем EXIF данные
        extract_exif_data(photo)
        
        return JsonResponse({
            'success': True,
            'photo_id': photo.id,
            'message': 'Фотография успешно загружена и сразу доступна в галерее'
        })

    except Exception as e:
        logger.exception("Ошибка загрузки фотографии")
        return JsonResponse({'error': str(e)}, status=500)


def download_photo(request, photo_id):
    """Скачивание фотографии"""
    photo = get_object_or_404(Photo, id=photo_id, is_approved=True)
    
    if not request.user.is_authenticated:
        messages.warning(request, 'Авторизуйтесь, чтобы скачать купленные изображения.')
        login_url = reverse('accounts:login') + f'?next={request.path}'
        return redirect(login_url)

    is_author = request.user == photo.author or request.user.is_staff
    has_license = user_has_active_license(request.user, photo)

    if not (is_author or has_license):
        messages.error(request, 'Скачивание доступно после покупки подходящей лицензии.')
        return redirect('gallery:photo_detail', photo_id=photo.id)

    # Записываем скачивание
    ip_address = get_client_ip(request)
    PhotoDownload.objects.get_or_create(
        photo=photo,
        user=request.user,
        ip_address=ip_address
    )
    
    photo.increment_downloads()
    
    # Возвращаем файл потоково
    photo.image.open('rb')
    return FileResponse(
        photo.image,
        as_attachment=True,
        filename=f"{photo.title}.jpg",
        content_type='application/octet-stream'
    )


@api_view(['POST'])
def extract_metadata_api(request):
    """API для извлечения метаданных из файла"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Необходимо войти в систему'}, status=401)
    
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Файл не выбран'}, status=400)
    
    file = request.FILES['file']
    
    if not file.content_type.startswith('image/'):
        return JsonResponse({'error': 'Файл должен быть изображением'}, status=400)
    
    temp_path = None
    try:
        # Временно сохраняем файл
        temp_path = default_storage.save(f'temp/{file.name}', ContentFile(file.read()))
        full_temp_path = default_storage.path(temp_path)

        # Извлекаем метаданные
        metadata = extract_file_metadata(full_temp_path)

        return JsonResponse({
            'success': True,
            'metadata': metadata
        })

    except Exception as e:
        logger.exception("Ошибка извлечения метаданных")
        return JsonResponse({'error': f'Ошибка извлечения метаданных: {str(e)}'}, status=500)
    finally:
        if temp_path:
            default_storage.delete(temp_path)


@api_view(['GET'])
def search_api(request):
    """API для поиска фотографий"""
    query = request.GET.get('q', '')
    category = request.GET.get('category', '')
    try:
        page = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        page = 1

    photos = (
        Photo.objects.filter(is_approved=True)
        .select_related('category', 'author', 'author__profile')
    )

    photos = apply_search_filters(photos, query)

    if category:
        photos = photos.filter(category__slug=category)

    photos = apply_smart_sorting(photos)

    paginator = Paginator(photos, 100)
    page_obj = paginator.get_page(page)

    data = {
        'photos': [{
            'id': photo.id,
            'title': photo.title,
            'thumbnail': photo.thumbnail.url if photo.thumbnail else photo.image.url,
            'author': photo.author.username,
            'views': photo.views,
            'downloads': photo.downloads,
        } for photo in page_obj],
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
        'page': page,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
    }

    return Response(data)


def get_client_ip(request):
    """Получает IP адрес клиента"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def decode_exif_string(value):
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


def extract_file_metadata(file_path):
    """Извлекает EXIF и IPTC метаданные из файла используя ExifTool"""
    metadata = {
        'exif': {},
        'iptc': {},
        'title': '',
        'description': '',
        'keywords': []
    }
    
    logger.debug("Extracting metadata from %s", file_path)
    
    # Метод 1: ExifTool через командную строку (самый надежный)
    try:
        # Запускаем exiftool для получения всех метаданных в JSON формате
        result = subprocess.run([
            'exiftool', 
            '-j',  # JSON output
            '-charset', 'utf8',  # Поддержка UTF-8 кодировки
            '-Title', '-Headline', '-ObjectName',  # Названия
            '-Description', '-Caption-Abstract', '-XPSubject',  # Описания
            '-Keywords', '-XPKeywords',  # Ключевые слова
            '-XPTitle',  # Windows XP Title
            file_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)[0]  # ExifTool возвращает массив
            logger.debug("ExifTool found %s metadata fields", len(data))
            
            # Извлекаем названия (приоритет: IPTC > XMP > EXIF)
            title_fields = [
                'Headline', 'IPTC:Headline',
                'ObjectName', 'IPTC:ObjectName', 
                'Title', 'XMP-dc:Title',
                'XPTitle', 'XP Title'
            ]
            
            for field in title_fields:
                if field in data and data[field] and not metadata['title']:
                    metadata['title'] = str(data[field]).strip()
                    metadata['iptc' if 'IPTC' in field else 'exif'][field] = metadata['title']
                    logger.debug("Title sourced from %s", field)
                    break
            
            # Извлекаем описания
            desc_fields = [
                'Caption-Abstract', 'IPTC:Caption-Abstract',
                'Description', 'XMP-dc:Description', 
                'ImageDescription', 'Image Description',
                'XPSubject', 'XP Subject'
            ]
            
            for field in desc_fields:
                if field in data and data[field] and not metadata['description']:
                    metadata['description'] = str(data[field]).strip()
                    metadata['iptc' if 'IPTC' in field else 'exif'][field] = metadata['description']
                    logger.debug("Description sourced from %s", field)
                    break
            
            # Извлекаем ключевые слова
            keyword_fields = [
                'Keywords', 'IPTC:Keywords',
                'XPKeywords', 'XP Keywords',
                'Subject', 'XMP-dc:Subject'
            ]
            
            for field in keyword_fields:
                if field in data and data[field] and not metadata['keywords']:
                    keywords_data = data[field]
                    
                    if isinstance(keywords_data, list):
                        metadata['keywords'] = [str(k).strip() for k in keywords_data if str(k).strip()]
                    elif isinstance(keywords_data, str):
                        # Пробуем разные разделители
                        keywords_str = keywords_data.strip()
                        keywords = []
                        for sep in [',', ';', '|', '\n', '\t']:
                            keywords = [k.strip() for k in keywords_str.split(sep) if k.strip()]
                            if len(keywords) > 1:
                                break
                        if not keywords and keywords_str:
                            keywords = [keywords_str]
                        metadata['keywords'] = keywords
                    
                    if metadata['keywords']:
                        metadata['iptc' if 'IPTC' in field else 'exif'][field] = metadata['keywords']
                        logger.debug("Keywords sourced from %s", field)
                        break
            
            # Показываем все найденные поля для отладки
            logger.debug("Sample of ExifTool fields: %s", list(data.keys())[:20])
            
        else:
            logger.warning("ExifTool failed: %s", result.stderr)
            
    except subprocess.TimeoutExpired:
        logger.warning("ExifTool timeout for %s", file_path)
    except FileNotFoundError:
        logger.info("ExifTool not found. Install with: apt install exiftool")
    except Exception as e:
        logger.exception("Error running ExifTool for %s", file_path)
    
    # Резервный метод: exifread (если ExifTool не сработал)
    if not metadata['title']:
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                
                for tag_name, tag_value in tags.items():
                    if 'XPTitle' in tag_name and not metadata['title']:
                        title = decode_exif_string(tag_value.values)
                        if title.strip():
                            metadata['title'] = title
                            metadata['exif']['XPTitle'] = title
                            logger.debug("Fallback title extracted from EXIF")
                    
                    elif 'XPKeywords' in tag_name and not metadata['keywords']:
                        keywords_str = decode_exif_string(tag_value.values)
                        if keywords_str.strip():
                            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                            if not keywords:
                                keywords = [k.strip() for k in keywords_str.split(';') if k.strip()]
                            metadata['keywords'] = keywords
                            metadata['exif']['XPKeywords'] = keywords_str
                            logger.debug("Fallback keywords extracted from EXIF")
                            
        except Exception:
            logger.exception("Error with fallback exifread for %s", file_path)
    
    logger.debug(
        "Metadata summary for %s | title=%s | description_len=%s | keywords_sample=%s",
        os.path.basename(file_path),
        metadata['title'],
        len(metadata['description']),
        metadata['keywords'][:3],
    )
    
    return metadata


def extract_exif_data(photo):
    """Извлекает EXIF данные из фотографии"""
    try:
        with open(photo.image.path, 'rb') as f:
            tags = exifread.process_file(f)
            
            # Можно добавить извлечение специфических тегов
            # Например: камера, настройки съемки, GPS координаты и т.д.
            
    except Exception as e:
        logger.warning("Ошибка извлечения EXIF для %s: %s", photo.pk, e)


@login_required
def user_photos(request):
    """Фотографии пользователя"""
    photos = Photo.objects.filter(author=request.user).select_related('category')

    # Применяем умную сортировку
    photos = apply_smart_sorting(photos)

    paginator = Paginator(photos, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    categories = Category.objects.all().order_by('name')

    context = {
        'photos': page_obj,
        'title': 'Мои фотографии',
        'categories': categories,
    }

    return render(request, 'gallery/user_photos.html', context)


@login_required
@require_http_methods(["POST"])
def manage_user_photos(request):
    """Обработка массовых действий с фотографиями пользователя"""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат запроса'}, status=400)

    action = payload.get('action')
    if action not in {'delete', 'delete_all', 'update'}:
        return JsonResponse({'error': 'Неизвестное действие'}, status=400)

    if action == 'delete':
        ids = payload.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return JsonResponse({'error': 'Не выбраны фотографии для удаления'}, status=400)

        photos = Photo.objects.filter(author=request.user, id__in=ids)
        deleted_count = photos.count()
        photos.delete()
        return JsonResponse({'success': True, 'deleted': deleted_count})
    
    if action == 'delete_all':
        photos = Photo.objects.filter(author=request.user)
        deleted_count = photos.count()
        
        if deleted_count == 0:
            return JsonResponse({'error': 'У вас нет фотографий для удаления'}, status=400)
        
        # Удаляем все фотографии пользователя
        photos.delete()
        
        logger.info(f"User {request.user.username} deleted all {deleted_count} photos")
        
        return JsonResponse({
            'success': True, 
            'deleted': deleted_count,
            'message': f'Удалено {deleted_count} фотографий'
        })

    photo_id = payload.get('id')
    if not photo_id:
        return JsonResponse({'error': 'Не указана фотография для обновления'}, status=400)

    photo = get_object_or_404(Photo, id=photo_id, author=request.user)

    title = payload.get('title', '').strip()
    description = payload.get('description', '').strip()
    keywords = payload.get('keywords', '').strip()
    category_id = payload.get('category')

    if title:
        photo.title = title[:200]
    if description is not None:
        photo.description = description
    if keywords is not None:
        photo.keywords = keywords[:500]

    if category_id:
        try:
            photo.category = Category.objects.get(id=int(category_id))
        except (Category.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': 'Категория не найдена'}, status=400)
    else:
        photo.category = None

    photo.save(update_fields=['title', 'description', 'keywords', 'category', 'updated_at'])

    return JsonResponse({
        'success': True,
        'photo': {
            'id': photo.id,
            'title': photo.title,
            'description': photo.description,
            'keywords': photo.keywords,
            'category': photo.category.name if photo.category else '',
            'category_id': photo.category.id if photo.category else '',
            'uploaded_at': photo.uploaded_at.strftime('%d.%m.%Y'),
        }
    })
