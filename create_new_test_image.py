#!/usr/bin/env python3
"""
Создает новое тестовое изображение для проверки загрузки
"""

from PIL import Image, ImageDraw, ImageFont
import os
import time

def create_test_image():
    # Создаем новое изображение
    width, height = 800, 600
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Добавляем текст с уникальным временем
    timestamp = str(int(time.time()))
    text = f"Test Image\n{timestamp}"
    
    # Рисуем прямоугольник
    draw.rectangle([50, 50, width-50, height-50], fill='lightblue', outline='blue', width=3)
    
    # Добавляем текст
    try:
        # Пытаемся использовать системный шрифт
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 36)
    except:
        # Используем дефолтный шрифт
        font = ImageFont.load_default()
    
    # Вычисляем позицию для центрирования текста
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = (width - text_width) // 2
    text_y = (height - text_height) // 2
    
    draw.text((text_x, text_y), text, fill='black', font=font)
    
    # Сохраняем изображение
    filename = f"test_image_{timestamp}.jpg"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    image.save(filepath, 'JPEG', quality=95)
    
    print(f"✅ Создано тестовое изображение: {filename}")
    print(f"📁 Путь: {filepath}")
    print(f"📏 Размер: {width}x{height}")
    
    return filepath

if __name__ == "__main__":
    create_test_image()
