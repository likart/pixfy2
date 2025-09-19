from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

from gallery.models import Photo
from .models import LicenseType, OrderItem

CartData = Dict[str, Dict[str, int | str]]

CART_SESSION_KEY = 'store_cart'


def get_cart(request) -> CartData:
    return request.session.get(CART_SESSION_KEY, {})


def save_cart(request, cart: CartData) -> None:
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def clear_cart(request) -> None:
    if CART_SESSION_KEY in request.session:
        del request.session[CART_SESSION_KEY]
        request.session.modified = True


def cart_items_with_totals(cart: CartData) -> Tuple[List[dict], Decimal]:
    if not cart:
        return [], Decimal('0.00')

    photo_ids = {item['photo_id'] for item in cart.values() if 'photo_id' in item}
    license_slugs = {item['license_slug'] for item in cart.values() if 'license_slug' in item}

    photos = {
        photo.id: photo for photo in Photo.objects.filter(id__in=photo_ids, is_approved=True).select_related('author')
    }
    licenses = {
        lic.slug: lic for lic in LicenseType.objects.filter(slug__in=license_slugs, is_active=True)
    }

    items = []
    total = Decimal('0.00')

    for key, data in cart.items():
        photo = photos.get(data.get('photo_id'))
        license_type = licenses.get(data.get('license_slug'))
        if not photo or not license_type:
            continue
        price = license_type.get_price_for_photo(photo)
        items.append({
            'key': key,
            'photo': photo,
            'license': license_type,
            'price': price,
        })
        total += price

    return items, total


def user_has_active_license(user, photo: Photo) -> bool:
    if not user.is_authenticated:
        return False
    return OrderItem.objects.filter(
        order__user=user,
        order__status__in=['paid', 'completed'],
        photo=photo,
    ).exists()
