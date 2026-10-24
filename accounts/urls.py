from django.urls import path
from accounts.views import (
    login_page,
    logout_page,
    register_page,
    activate_email,
    add_to_cart,
    cart_page,
    apply_coupon,
    remove_coupon,
    remove_cart,
    start_payment,
    payment_checkout,
    verify_payment,
    payment_failed,
    payment_success,
)

urlpatterns = [
   path('login/' , login_page , name="login" ), 
   path('logout/', logout_page, name="logout"),
   path('register/' , register_page , name="register"),
   path('activate/<email_token>/' , activate_email , name="activate_email"),
   path('add-to-cart/<uid>/', add_to_cart, name="add_to_cart"),
   path('cart/', cart_page, name="cart"),
   path('cart/apply-coupon/', apply_coupon, name="apply_coupon"),
   path('cart/remove-coupon/', remove_coupon, name="remove_coupon"),
   path('remove-cart/<cart_item_uid>/', remove_cart, name="remove_cart"),
   path('cart/payment/start/', start_payment, name="start_payment"),
   path('cart/payment/verify/', verify_payment, name="verify_payment"),
   path('cart/payment/failed/', payment_failed, name="payment_failed"),
   path('cart/payment/<payment_uid>/', payment_checkout, name="payment_checkout"),
   path('cart/payment/<payment_uid>/success/', payment_success, name="payment_success"),

]   