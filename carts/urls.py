from django.urls import path
from . import views

urlpatterns = [
    path('', views.cart, name='cart'),
    path('add_cart/<int:product_id>/', views.add_cart, name='add_cart'),
    path('remove_cart/<int:product_id>/<int:cart_item_id>/', views.remove_cart, name='remove_cart'),
    path('remove_cart_item/<int:product_id>/<int:cart_item_id>/', views.remove_cart_item, name='remove_cart_item'),
    path('checkout/', views.checkout, name='checkout'),
    path('esewa/<int:product_id>/', views.buy, name='esewa_payment'),   # ✅ product_id
    path('success/<str:uid>/', views.success, name='esewa_success'),    # ✅ str:uid
    path('failure/<str:uid>/', views.failure, name='esewa_failure'),    # ✅ added failure
]