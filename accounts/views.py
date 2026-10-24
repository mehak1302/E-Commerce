from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from requests.exceptions import RequestException
import razorpay
# Models import
from .models import Profile, Cart, CartItems, RazorpayPayment
from products.models import Coupon, Product


def login_page(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user_obj = User.objects.filter(username=email)

        if not user_obj.exists():
            messages.warning(request, 'Account not found.')
            return HttpResponseRedirect(request.path_info)

        if not user_obj[0].profile.is_email_verified:
            messages.warning(request, 'Your account is not verified.')
            return HttpResponseRedirect(request.path_info)

        user_obj = authenticate(username=email, password=password)
        if user_obj:
            login(request, user_obj)
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('index')

        messages.warning(request, 'Invalid credentials')
        return HttpResponseRedirect(request.path_info)

    return render(request, 'accounts/login.html')


@login_required
@require_POST
def logout_page(request):
    logout(request)
    messages.success(request, 'You have been signed out.')
    return redirect('index')


def register_page(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        user_obj = User.objects.filter(username=email)

        if user_obj.exists():
            messages.warning(request, 'Email is already taken.')
            return HttpResponseRedirect(request.path_info)

        user_obj = User.objects.create(first_name=first_name, last_name=last_name, email=email, username=email)
        user_obj.set_password(password)
        user_obj.save()

        messages.success(request, 'An email has been sent on your mail.')
        return HttpResponseRedirect(request.path_info)

    return render(request, 'accounts/register.html')


def activate_email(request, email_token):
    try:
        user = Profile.objects.get(email_token=email_token)
        user.is_email_verified = True
        user.save()
        return redirect('/')
    except Exception as e:
        return HttpResponse('Invalid Email token')


# --- Cart Functions ---

@login_required
def add_to_cart(request, uid):
    if request.method != 'POST':
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    product = get_object_or_404(Product, uid=uid)
    variant = request.POST.get('size_variant')
    size_variant = None
    if variant:
        size_variant = get_object_or_404(product.size_variant, size_name=variant)
    color_name = request.POST.get('color_variant')
    color_variant = None
    if color_name:
        color_variant = get_object_or_404(product.color_variant, color_name=color_name)
    try:
        quantity = int(request.POST.get('quantity', '1'))
    except (TypeError, ValueError):
        messages.error(request, 'Please enter a valid quantity.')
        return redirect('get_product', slug=product.slug)
    if quantity < 1 or quantity > 99:
        messages.error(request, 'Quantity must be between 1 and 99.')
        return redirect('get_product', slug=product.slug)

    cart, _ = Cart.objects.get_or_create(user=request.user, is_paid=False)
    if cart.payments.filter(status=RazorpayPayment.Status.CREATED).exists():
        messages.warning(request, 'Finish or close your pending payment before changing the cart.')
        return redirect('cart')

    CartItems.objects.create(
        cart=cart,
        product=product,
        size_variant=size_variant,
        color_variant=color_variant,
        quantity=quantity,
    )

    if request.POST.get('buy_now') == '1':
        return _start_cart_payment(request, cart)

    return redirect('cart')

@login_required
def cart_page(request):
    cart = Cart.objects.filter(user=request.user, is_paid=False).first()
    cart_items = cart.cart_items.select_related(
        'product', 'size_variant'
    ).all() if cart else []
    subtotal = cart.get_subtotal() if cart else 0
    available_coupons = Coupon.objects.filter(is_expired=False).order_by(
        'minimum_amount', 'discount_price'
    )
    coupon_offers = [
        {
            'coupon': coupon,
            'amount_to_unlock': max(coupon.minimum_amount - subtotal, 0),
        }
        for coupon in available_coupons
    ]
    pending_payment = (
        cart.payments.filter(status=RazorpayPayment.Status.CREATED).first()
        if cart
        else None
    )
    return render(request, 'accounts/cart.html', {
        'cart': cart,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'coupon_discount': cart.get_coupon_discount() if cart else 0,
        'cart_coupon_amount_to_unlock': (
            max(cart.coupon.minimum_amount - subtotal, 0)
            if cart and cart.coupon
            else 0
        ),
        'coupon_offers': coupon_offers,
        'pending_payment': pending_payment,
    })

@login_required
def apply_coupon(request):
    if request.method != 'POST':
        return redirect('cart')

    cart = Cart.objects.filter(user=request.user, is_paid=False).first()
    coupon_code = request.POST.get('coupon_code', '').strip()
    if not cart or not cart.cart_items.exists():
        messages.warning(request, 'Add an item to your cart before applying a coupon.')
        return redirect('cart')

    if cart.payments.filter(status=RazorpayPayment.Status.CREATED).exists():
        messages.warning(request, 'Finish or close your pending payment before changing the cart.')
        return redirect('cart')

    coupon = Coupon.objects.filter(coupon_code__iexact=coupon_code).first()
    if not coupon or coupon.is_expired:
        messages.error(request, 'This coupon code is invalid or expired.')
        return redirect('cart')

    subtotal = sum(item.get_total_price() for item in cart.cart_items.all())
    if subtotal < coupon.minimum_amount:
        messages.warning(
            request,
            f'{coupon.coupon_name or coupon.coupon_code} needs a ₹{coupon.minimum_amount}.00 minimum. '
            f'Add ₹{coupon.minimum_amount - subtotal}.00 more to use it.',
        )
        return redirect('cart')

    cart.coupon = coupon
    cart.save(update_fields=['coupon'])
    messages.success(
        request,
        f'{coupon.coupon_name or coupon.coupon_code} applied! '
        f'You saved ₹{min(coupon.discount_price, subtotal)}.00.',
    )
    return redirect('cart')

@login_required
def remove_coupon(request):
    if request.method == 'POST':
        cart = Cart.objects.filter(user=request.user, is_paid=False).first()
        if cart and cart.payments.filter(status=RazorpayPayment.Status.CREATED).exists():
            messages.warning(request, 'Finish or close your pending payment before changing the cart.')
            return redirect('cart')
        if cart:
            cart.coupon = None
            cart.save(update_fields=['coupon'])
        messages.success(request, 'Coupon removed.')
    return redirect('cart')

@login_required
def remove_cart(request, cart_item_uid):
    cart_item = get_object_or_404(
        CartItems,
        uid=cart_item_uid,
        cart__user=request.user,
        cart__is_paid=False,
    )
    if cart_item.cart.payments.filter(status=RazorpayPayment.Status.CREATED).exists():
        messages.warning(request, 'Finish or close your pending payment before changing the cart.')
        return redirect('cart')
    cart_item.delete()
    return redirect('cart')


def _razorpay_client():
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
    if not key_id or not key_secret:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def _start_cart_payment(request, cart):
    if not cart.cart_items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')

    amount_paise = cart.get_cart_total() * 100
    if amount_paise <= 0:
        messages.error(request, 'The cart total must be greater than zero to make a purchase.')
        return redirect('cart')

    client = _razorpay_client()
    if client is None:
        messages.error(
            request,
            'Razorpay is not configured. Add KEY_ID and KEY_SECRET to your .env file.',
        )
        return redirect('cart')

    existing_payment = cart.payments.filter(
        status=RazorpayPayment.Status.CREATED,
    ).first()
    if existing_payment:
        if existing_payment.amount_paise != amount_paise:
            messages.error(
                request,
                'The cart total changed while a payment was pending. Close that payment and try again.',
            )
            return redirect('cart')
        return redirect('payment_checkout', payment_uid=existing_payment.uid)

    try:
        order = client.order.create(data={
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'cart-{str(cart.uid).replace("-", "")[:32]}',
            'notes': {
                'cart_id': str(cart.uid),
                'customer_id': str(request.user.pk),
            },
        })
    except (razorpay.errors.BadRequestError,
            razorpay.errors.GatewayError,
            razorpay.errors.ServerError,
            RequestException) as exc:
        messages.error(request, f'Razorpay could not create the order: {exc}')
        return redirect('cart')

    payment = RazorpayPayment.objects.create(
        cart=cart,
        razorpay_order_id=order['id'],
        amount_paise=amount_paise,
        currency='INR',
    )
    return redirect('payment_checkout', payment_uid=payment.uid)


@login_required
def start_payment(request):
    if request.method != 'POST':
        return redirect('cart')

    cart = Cart.objects.filter(user=request.user, is_paid=False).first()
    if not cart or not cart.cart_items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')

    return _start_cart_payment(request, cart)


@login_required
def payment_checkout(request, payment_uid):
    payment = get_object_or_404(
        RazorpayPayment,
        uid=payment_uid,
        cart__user=request.user,
    )
    if payment.status == RazorpayPayment.Status.PAID:
        return redirect('payment_success', payment_uid=payment.uid)
    if payment.status != RazorpayPayment.Status.CREATED:
        messages.warning(request, 'This payment attempt is no longer active. Please try again.')
        return redirect('cart')
    return render(request, 'accounts/payment_checkout.html', {
        'payment': payment,
        'amount_rupees': payment.amount_paise // 100,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'customer_name': request.user.get_full_name() or request.user.username,
        'customer_email': request.user.email,
    })


@login_required
def verify_payment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    order_id = request.POST.get('razorpay_order_id', '')
    payment_id = request.POST.get('razorpay_payment_id', '')
    signature = request.POST.get('razorpay_signature', '')
    if not order_id or not payment_id or not signature:
        return JsonResponse({'error': 'Payment verification details are incomplete.'}, status=400)

    payment = get_object_or_404(
        RazorpayPayment,
        razorpay_order_id=order_id,
        cart__user=request.user,
    )
    if payment.status == RazorpayPayment.Status.PAID:
        return JsonResponse({'redirect_url': reverse('payment_success', args=[payment.uid])})
    if payment.status != RazorpayPayment.Status.CREATED:
        return JsonResponse({'error': 'This payment attempt is no longer active.'}, status=400)

    client = _razorpay_client()
    if client is None:
        return JsonResponse({'error': 'Razorpay is not configured on the server.'}, status=503)

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
        })
        payment_details = client.payment.fetch(payment_id)
        if (
            payment_details.get('order_id') != payment.razorpay_order_id
            or payment_details.get('amount') != payment.amount_paise
            or payment_details.get('currency') != payment.currency
        ):
            return JsonResponse(
                {'error': 'Razorpay payment details do not match this order.'},
                status=400,
            )
        if payment_details.get('status') == 'authorized':
            payment_details = client.payment.capture(
                payment_id,
                payment.amount_paise,
                {'currency': payment.currency},
            )
    except razorpay.errors.SignatureVerificationError:
        payment.status = RazorpayPayment.Status.FAILED
        payment.failure_reason = 'Payment signature verification failed.'
        payment.save(update_fields=['status', 'failure_reason'])
        return JsonResponse({'error': 'Payment could not be verified. No order was placed.'}, status=400)
    except (razorpay.errors.BadRequestError,
            razorpay.errors.GatewayError,
            razorpay.errors.ServerError,
            RequestException) as exc:
        return JsonResponse({'error': f'Razorpay verification failed: {exc}'}, status=502)

    if payment_details.get('status') != 'captured':
        return JsonResponse(
            {'error': 'Razorpay has not confirmed a captured payment for this order.'},
            status=400,
        )

    with transaction.atomic():
        payment = RazorpayPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == RazorpayPayment.Status.PAID:
            return JsonResponse({'redirect_url': reverse('payment_success', args=[payment.uid])})
        if payment.status != RazorpayPayment.Status.CREATED:
            return JsonResponse({'error': 'This payment attempt is no longer active.'}, status=400)

        cart = Cart.objects.select_for_update().get(pk=payment.cart_id)
        payment.status = RazorpayPayment.Status.PAID
        payment.razorpay_payment_id = payment_id
        payment.save(update_fields=['status', 'razorpay_payment_id'])
        cart.is_paid = True
        cart.save(update_fields=['is_paid'])

    return JsonResponse({'redirect_url': reverse('payment_success', args=[payment.uid])})


@login_required
def payment_failed(request):
    if request.method != 'POST':
        return redirect('cart')

    payment = get_object_or_404(
        RazorpayPayment,
        uid=request.POST.get('payment_uid'),
        cart__user=request.user,
        status=RazorpayPayment.Status.CREATED,
    )
    payment.status = RazorpayPayment.Status.FAILED
    payment.failure_reason = 'Payment was cancelled or failed in checkout.'
    payment.save(update_fields=['status', 'failure_reason'])
    messages.warning(request, 'Payment was not completed. You can try again from your cart.')
    return redirect('cart')


@login_required
def payment_success(request, payment_uid):
    payment = get_object_or_404(
        RazorpayPayment,
        uid=payment_uid,
        cart__user=request.user,
        status=RazorpayPayment.Status.PAID,
    )
    return render(request, 'accounts/payment_success.html', {
        'payment': payment,
        'amount_rupees': payment.amount_paise // 100,
    })



