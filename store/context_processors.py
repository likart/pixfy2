from .services import get_cart


def cart_summary(request):
    cart = get_cart(request)
    return {
        'cart_item_count': len(cart),
    }
