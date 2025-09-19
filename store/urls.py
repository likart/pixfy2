from django.urls import path

from . import views

app_name = 'store'

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:photo_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<str:item_key>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<str:item_key>/', views.update_cart_item, name='update_cart_item'),
    path('checkout/', views.checkout, name='checkout'),
    path('payment/<int:order_id>/', views.payment_placeholder, name='payment'),
    path('payment/<int:order_id>/confirm/', views.simulate_payment, name='simulate_payment'),
    path('orders/', views.order_list, name='orders'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/item/<int:item_id>/download/', views.download_order_item, name='download_order_item'),
    path('licenses/', views.license_list, name='licenses'),
    path('pricing/', views.pricing, name='pricing'),
]
