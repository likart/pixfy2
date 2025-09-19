from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from gallery.models import Photo
from .forms import CheckoutForm
from .models import LicenseType, Order, OrderItem
from .services import (
    CART_SESSION_KEY,
    cart_items_with_totals,
    clear_cart,
    get_cart,
    save_cart,
    user_has_active_license,
)


def _default_license() -> LicenseType | None:
    return LicenseType.objects.filter(is_active=True).order_by('sort_order', 'id').first()


def _ensure_client(request):
    if request.user.is_authenticated and getattr(getattr(request.user, 'profile', None), 'is_contributor', False):
        messages.error(request, 'Авторский аккаунт не предназначен для покупок. Используйте клиентский аккаунт.')
        return redirect('gallery:home')
    return None


def cart_view(request):
    guard = _ensure_client(request)
    if guard:
        return guard
    cart = get_cart(request)
    items, total = cart_items_with_totals(cart)
    licenses = LicenseType.objects.filter(is_active=True).order_by('sort_order', 'id')
    context = {
        'items': items,
        'total': total,
        'licenses': licenses,
    }
    return render(request, 'store/cart.html', context)


@require_POST
def add_to_cart(request, photo_id):
    guard = _ensure_client(request)
    if guard:
        return guard
    photo = get_object_or_404(Photo, id=photo_id, is_approved=True)
    license_slug = request.POST.get('license')

    license_type = None
    if license_slug:
        license_type = LicenseType.objects.filter(slug=license_slug, is_active=True).first()
    if license_type is None:
        license_type = _default_license()
    if license_type is None:
        messages.error(request, 'Нет доступных лицензий для покупки.')
        return redirect(request.POST.get('next') or reverse('gallery:photo_detail', args=[photo.id]))

    cart = get_cart(request)
    key = f"{photo.id}:{license_type.slug}"
    cart[key] = {
        'photo_id': photo.id,
        'license_slug': license_type.slug,
    }
    save_cart(request, cart)
    messages.success(request, f'Фотография «{photo.title}» добавлена в корзину')

    next_url = request.POST.get('next') or reverse('store:cart')
    return redirect(next_url)


@require_POST
def remove_from_cart(request, item_key):
    guard = _ensure_client(request)
    if guard:
        return guard
    cart = get_cart(request)
    if item_key in cart:
        del cart[item_key]
        save_cart(request, cart)
        messages.info(request, 'Позиция удалена из корзины.')
    return redirect('store:cart')


@require_POST
def update_cart_item(request, item_key):
    guard = _ensure_client(request)
    if guard:
        return guard
    cart = get_cart(request)
    if item_key not in cart:
        return redirect('store:cart')

    new_license_slug = request.POST.get('license')
    license_type = LicenseType.objects.filter(slug=new_license_slug, is_active=True).first()
    if not license_type:
        messages.error(request, 'Выбранная лицензия недоступна.')
        return redirect('store:cart')

    cart[item_key]['license_slug'] = license_type.slug
    # ключ зависит от лицензии, пересоздадим его
    data = cart.pop(item_key)
    new_key = f"{data['photo_id']}:{license_type.slug}"
    cart[new_key] = data
    save_cart(request, cart)
    messages.success(request, 'Лицензия обновлена.')
    return redirect('store:cart')


@login_required
def checkout(request):
    guard = _ensure_client(request)
    if guard:
        return guard
    cart = get_cart(request)
    items, total = cart_items_with_totals(cart)
    if not items:
        messages.info(request, 'Добавьте фотографии в корзину перед оформлением.')
        return redirect('store:cart')

    initial = {
        'full_name': request.user.get_full_name() or request.user.username,
        'email': request.user.email,
    }

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user,
                    full_name=form.cleaned_data['full_name'],
                    email=form.cleaned_data['email'],
                    company=form.cleaned_data['company'],
                    notes=form.cleaned_data['notes'],
                    status=Order.STATUS_AWAITING_PAYMENT,
                    total_amount=Decimal('0.00'),
                )
                for item in items:
                    OrderItem.objects.create(
                        order=order,
                        photo=item['photo'],
                        license_type=item['license'],
                        unit_price=item['price'],
                    )
                order.recalc_totals()
            clear_cart(request)
            messages.success(request, 'Заказ создан. Ожидается оплата.')
            return redirect('store:payment', order_id=order.id)
    else:
        form = CheckoutForm(initial=initial)

    return render(
        request,
        'store/checkout.html',
        {
            'items': items,
            'total': total,
            'form': form,
        }
    )


@login_required
def payment_placeholder(request, order_id):
    guard = _ensure_client(request)
    if guard:
        return guard
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status in {Order.STATUS_PAID, Order.STATUS_COMPLETED}:
        return redirect('store:order_detail', order_id=order.id)
    return render(request, 'store/payment_placeholder.html', {'order': order})


@login_required
@require_POST
def simulate_payment(request, order_id):
    guard = _ensure_client(request)
    if guard:
        return guard
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status not in {Order.STATUS_PAID, Order.STATUS_COMPLETED}:
        order.status = Order.STATUS_PAID
        order.payment_reference = f"SIM-{order.id:06d}"
        order.save(update_fields=['status', 'payment_reference', 'updated_at'])
        messages.success(request, 'Оплата подтверждена (демо). Доступ к скачиванию открыт.')
    return redirect('store:order_detail', order_id=order.id)


@login_required
def order_list(request):
    guard = _ensure_client(request)
    if guard:
        return guard
    orders = request.user.orders.prefetch_related('items__photo', 'items__license_type')
    return render(request, 'store/order_list.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    guard = _ensure_client(request)
    if guard:
        return guard
    order = get_object_or_404(Order.objects.prefetch_related('items__photo', 'items__license_type'), id=order_id, user=request.user)
    return render(request, 'store/order_detail.html', {'order': order})


@login_required
def download_order_item(request, item_id):
    guard = _ensure_client(request)
    if guard:
        return guard
    item = get_object_or_404(OrderItem.objects.select_related('order', 'photo'), id=item_id, order__user=request.user)
    if item.order.status not in {Order.STATUS_PAID, Order.STATUS_COMPLETED}:
        return HttpResponseForbidden('Оплатите заказ, чтобы получить доступ к файлам.')
    photo = item.photo
    photo.image.open('rb')
    return FileResponse(
        photo.image,
        as_attachment=True,
        filename=f"{photo.title}.jpg",
        content_type='application/octet-stream'
    )


def license_list(request):
    licenses = LicenseType.objects.filter(is_active=True).order_by('sort_order', 'id')
    return render(request, 'store/license_list.html', {'licenses': licenses})


def pricing(request):
    licenses = LicenseType.objects.filter(is_active=True).order_by('sort_order', 'id')
    bundles = [
        {
            'name': 'Стартовый пакет',
            'description': '5 загрузок со стандартной лицензией',
            'price': '$39',
            'features': ['Доступ к коллекции PixFy', 'Использование в вебе и соцсетях', 'Поддержка 24/7'],
        },
        {
            'name': 'Бизнес',
            'description': '20 загрузок с любой лицензией',
            'price': '$149',
            'features': ['Расширенная лицензия входит', 'До 5 участников команды', 'Приоритетная поддержка'],
        },
        {
            'name': 'Агентство',
            'description': 'Безлимитные загрузки и неограниченная лицензия',
            'price': 'Свяжитесь с нами',
            'features': ['Неограниченные тиражи', 'Перепродажа в шаблонах', 'Персональный менеджер'],
        },
    ]
    return render(request, 'store/pricing.html', {
        'licenses': licenses,
        'bundles': bundles,
    })
