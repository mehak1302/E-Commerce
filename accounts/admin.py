from django.contrib import admin

from .models import Cart, CartItems, Profile, RazorpayPayment


@admin.register(RazorpayPayment)
class RazorpayPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'razorpay_order_id',
        'cart',
        'amount_paise',
        'currency',
        'status',
        'created_at',
    ]
    list_filter = ['status', 'currency']
    search_fields = ['razorpay_order_id', 'razorpay_payment_id', 'cart__user__username']
    readonly_fields = [
        'cart',
        'razorpay_order_id',
        'razorpay_payment_id',
        'amount_paise',
        'currency',
        'status',
        'failure_reason',
        'created_at',
        'updated_at',
    ]


admin.site.register(Profile)
admin.site.register(Cart)
admin.site.register(CartItems)
