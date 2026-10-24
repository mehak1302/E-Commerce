from django.db import models
from django.contrib.auth.models import User
from base.models import BaseModel
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid
from base.emails import send_account_activation_email
from products.models import Coupon, Product, ColorVariant, SizeVariant


class Profile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    is_email_verified = models.BooleanField(default=False)
    email_token = models.CharField(max_length=100, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profile', null=True, blank=True)

    def __str__(self):
        return self.user.username

  
    def get_cart_count(self):
        return CartItems.objects.filter(cart__is_paid=False, cart__user=self.user).count()


@receiver(post_save, sender=User)
def send_email_token(sender, instance, created, **kwargs):
    try:
        if created:
            email_token = str(uuid.uuid4())
            Profile.objects.create(user=instance, email_token=email_token)
            
            if instance.email:
                send_account_activation_email(instance.email, email_token)

    except Exception as e:
        print(f"Error in post_save signal: {e}")


class Cart(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='carts')
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    is_paid = models.BooleanField(default=False)

    def get_subtotal(self):
        return sum(item.get_total_price() for item in self.cart_items.all())

    def get_coupon_discount(self):
        if not self.coupon or self.coupon.is_expired:
            return 0

        if self.get_subtotal() < self.coupon.minimum_amount:
            return 0

        return min(self.coupon.discount_price, self.get_subtotal())

    def get_cart_total(self):
        return self.get_subtotal() - self.get_coupon_discount()


class CartItems(BaseModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    color_variant = models.ForeignKey(ColorVariant, on_delete=models.SET_NULL, null=True, blank=True)
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    def get_total_price(self):
        if not self.product:
            return 0

        price = self.product.price
        if self.color_variant:
            price += self.color_variant.price
        if self.size_variant:
            price += self.size_variant.price
        return price * self.quantity


class RazorpayPayment(BaseModel):
    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'

    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name='payments')
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.CREATED,
    )
    failure_reason = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f'{self.razorpay_order_id} ({self.status})'