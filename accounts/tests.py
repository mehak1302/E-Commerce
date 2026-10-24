from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Cart, CartItems, RazorpayPayment
from products.models import Category, ColorVariant, Coupon, Product, SizeVariant
from unittest.mock import Mock, patch


class CartFlowTests(TestCase):
    def setUp(self):
        category = Category.objects.create(category_name="Cart category")
        self.product = Product.objects.create(
            product_name="Cart product",
            category=category,
            price=100,
            product_desription="Test description",
        )
        self.size = SizeVariant.objects.create(size_name="Large", price=25)
        self.product.size_variant.add(self.size)
        self.user = User.objects.create_user(
            username="cart-user",
            password="test-password",
        )

    def test_add_to_cart_opens_cart_with_selected_size_and_price(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("add_to_cart", args=[self.product.uid]),
            {"size_variant": self.size.size_name},
        )

        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(CartItems.objects.count(), 1)
        cart_item = CartItems.objects.get()
        self.assertEqual(cart_item.size_variant, self.size)
        self.assertEqual(cart_item.get_total_price(), 125)
        self.assertContains(self.client.get(reverse("cart")), "₹125.00")

    def test_add_to_cart_requires_login(self):
        response = self.client.post(
            reverse("add_to_cart", args=[self.product.uid]),
            {"size_variant": self.size.size_name},
        )

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('add_to_cart', args=[self.product.uid])}",
        )
        self.assertFalse(Cart.objects.exists())

    def test_add_to_cart_saves_quantity_and_selected_color(self):
        red = ColorVariant.objects.create(color_name="Red", price=15)
        self.product.color_variant.add(red)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("add_to_cart", args=[self.product.uid]),
            {
                "size_variant": self.size.size_name,
                "color_variant": red.color_name,
                "quantity": "3",
            },
        )

        item = CartItems.objects.get()
        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(item.size_variant, self.size)
        self.assertEqual(item.color_variant, red)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.get_total_price(), 420)
        self.assertEqual(item.cart.get_subtotal(), 420)

    def test_invalid_quantity_does_not_add_item(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("add_to_cart", args=[self.product.uid]),
            {"quantity": "0"},
        )

        self.assertRedirects(response, reverse("get_product", args=[self.product.slug]))
        self.assertFalse(CartItems.objects.exists())

    def test_header_has_working_account_and_info_links(self):
        response = self.client.get(reverse("index"))

        self.assertContains(response, reverse("login"))
        self.assertContains(response, reverse("register"))
        self.assertContains(response, f"{reverse('index')}#delivery")
        self.assertContains(response, f"{reverse('index')}#payment")

    def test_sign_out_requires_post_and_signs_user_out(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("index"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_returns_to_safe_next_url(self):
        self.user.profile.is_email_verified = True
        self.user.profile.save(update_fields=["is_email_verified"])

        response = self.client.post(
            reverse("login") + "?next=" + reverse("cart"),
            {
                "email": self.user.username,
                "password": "test-password",
                "next": reverse("cart"),
            },
        )

        self.assertRedirects(response, reverse("cart"))

    def test_login_rejects_external_next_url(self):
        self.user.profile.is_email_verified = True
        self.user.profile.save(update_fields=["is_email_verified"])

        response = self.client.post(
            reverse("login"),
            {
                "email": self.user.username,
                "password": "test-password",
                "next": "https://example.com/",
            },
        )

        self.assertRedirects(response, reverse("index"))

    def test_coupon_is_applied_and_discounted_total_is_displayed(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(
            cart=cart,
            product=self.product,
            size_variant=self.size,
        )
        coupon = Coupon.objects.create(
            coupon_name="Cart saver",
            coupon_code="SAVE20",
            description="Save ₹20 when your cart is at least ₹100.",
            discount_price=20,
            minimum_amount=100,
        )

        response = self.client.post(
            reverse("apply_coupon"),
            {"coupon_code": "save20"},
        )

        self.assertRedirects(response, reverse("cart"))
        cart.refresh_from_db()
        self.assertEqual(cart.coupon, coupon)
        self.assertEqual(cart.get_cart_total(), 105)
        cart_response = self.client.get(reverse("cart"))
        self.assertContains(cart_response, "₹105.00")
        self.assertContains(cart_response, "Cart saver")
        self.assertContains(cart_response, "SAVE20")
        self.assertContains(cart_response, "Save ₹20 when your cart is at least ₹100.")

    def test_expired_or_below_minimum_coupon_is_not_applied(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(cart=cart, product=self.product)
        expired_coupon = Coupon.objects.create(
            coupon_code="EXPIRED",
            is_expired=True,
            discount_price=10,
            minimum_amount=50,
        )
        Coupon.objects.create(
            coupon_code="TOOHIGH",
            discount_price=10,
            minimum_amount=200,
        )

        self.client.post(reverse("apply_coupon"), {"coupon_code": expired_coupon.coupon_code})
        cart.refresh_from_db()
        self.assertIsNone(cart.coupon)

        self.client.post(reverse("apply_coupon"), {"coupon_code": "TOOHIGH"})
        cart.refresh_from_db()
        self.assertIsNone(cart.coupon)

    def test_available_coupon_shows_minimum_and_amount_needed_to_unlock(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(cart=cart, product=self.product)
        Coupon.objects.create(
            coupon_name="Big basket deal",
            coupon_code="BIGBASKET",
            description="Save ₹30 on a bigger order.",
            discount_price=30,
            minimum_amount=200,
        )

        response = self.client.get(reverse("cart"))

        self.assertContains(response, "Big basket deal")
        self.assertContains(response, "BIGBASKET")
        self.assertContains(response, "Minimum order: ₹200")
        self.assertContains(response, "Add ₹100.00 more to unlock")

        response = self.client.post(
            reverse("apply_coupon"),
            {"coupon_code": "BIGBASKET"},
            follow=True,
        )

        self.assertContains(response, "Add ₹100.00 more to use it.")

    def test_coupon_discount_cannot_make_total_negative(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(cart=cart, product=self.product)
        coupon = Coupon.objects.create(
            coupon_code="BIGSAVE",
            discount_price=500,
            minimum_amount=50,
        )

        self.client.post(reverse("apply_coupon"), {"coupon_code": coupon.coupon_code})

        cart.refresh_from_db()
        self.assertEqual(cart.get_cart_total(), 0)

    @patch('accounts.views._razorpay_client')
    def test_make_purchase_creates_rupee_order_and_shows_razorpay_order_id(self, get_client):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(
            cart=cart,
            product=self.product,
            size_variant=self.size,
        )
        client = Mock()
        client.order.create.return_value = {'id': 'order_test_123'}
        get_client.return_value = client

        response = self.client.post(reverse('start_payment'))

        payment = RazorpayPayment.objects.get()
        self.assertRedirects(
            response,
            reverse('payment_checkout', args=[payment.uid]),
        )
        self.assertEqual(payment.amount_paise, 12500)
        self.assertEqual(payment.currency, 'INR')
        self.assertContains(
            self.client.get(reverse('payment_checkout', args=[payment.uid])),
            'order_test_123',
        )
        self.assertEqual(client.order.create.call_args.kwargs['data']['amount'], 12500)

    @patch('accounts.views._razorpay_client')
    def test_buy_now_adds_selected_quantity_and_starts_correct_payment(self, get_client):
        self.client.force_login(self.user)
        red = ColorVariant.objects.create(color_name="Red", price=15)
        self.product.color_variant.add(red)
        client = Mock()
        client.order.create.return_value = {'id': 'order_buy_now_123'}
        get_client.return_value = client

        response = self.client.post(
            reverse("add_to_cart", args=[self.product.uid]),
            {
                "size_variant": self.size.size_name,
                "color_variant": red.color_name,
                "quantity": "2",
                "buy_now": "1",
            },
        )

        item = CartItems.objects.get()
        payment = RazorpayPayment.objects.get()
        self.assertRedirects(
            response,
            reverse("payment_checkout", args=[payment.uid]),
        )
        self.assertEqual(item.get_total_price(), 280)
        self.assertEqual(payment.amount_paise, 28000)
        self.assertEqual(
            client.order.create.call_args.kwargs['data']['amount'],
            28000,
        )

    @patch('accounts.views._razorpay_client')
    def test_payment_is_marked_paid_only_after_signature_and_capture_verification(self, get_client):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(cart=cart, product=self.product)
        payment = RazorpayPayment.objects.create(
            cart=cart,
            razorpay_order_id='order_test_456',
            amount_paise=10000,
        )
        client = Mock()
        client.payment.fetch.return_value = {
            'order_id': payment.razorpay_order_id,
            'amount': payment.amount_paise,
            'currency': 'INR',
            'status': 'captured',
        }
        get_client.return_value = client

        response = self.client.post(
            reverse('verify_payment'),
            {
                'razorpay_order_id': payment.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_789',
                'razorpay_signature': 'valid-test-signature',
            },
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        cart.refresh_from_db()
        self.assertEqual(payment.status, RazorpayPayment.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, 'pay_test_789')
        self.assertTrue(cart.is_paid)
        self.assertEqual(
            response.json()['redirect_url'],
            reverse('payment_success', args=[payment.uid]),
        )
        self.assertContains(
            self.client.get(reverse('payment_success', args=[payment.uid])),
            'pay_test_789',
        )

    @patch('accounts.views._razorpay_client')
    def test_uncaptured_payment_does_not_mark_order_paid(self, get_client):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(cart=cart, product=self.product)
        payment = RazorpayPayment.objects.create(
            cart=cart,
            razorpay_order_id='order_test_uncaptured',
            amount_paise=10000,
        )
        client = Mock()
        client.payment.fetch.return_value = {
            'order_id': payment.razorpay_order_id,
            'amount': payment.amount_paise,
            'currency': 'INR',
            'status': 'failed',
        }
        get_client.return_value = client

        response = self.client.post(
            reverse('verify_payment'),
            {
                'razorpay_order_id': payment.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_uncaptured',
                'razorpay_signature': 'valid-test-signature',
            },
        )

        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        cart.refresh_from_db()
        self.assertEqual(payment.status, RazorpayPayment.Status.CREATED)
        self.assertFalse(cart.is_paid)

    @patch('accounts.views._razorpay_client')
    def test_authorized_payment_is_captured_before_cart_is_marked_paid(self, get_client):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItems.objects.create(cart=cart, product=self.product)
        payment = RazorpayPayment.objects.create(
            cart=cart,
            razorpay_order_id='order_test_authorized',
            amount_paise=10000,
        )
        client = Mock()
        client.payment.fetch.return_value = {
            'order_id': payment.razorpay_order_id,
            'amount': payment.amount_paise,
            'currency': 'INR',
            'status': 'authorized',
        }
        client.payment.capture.return_value = {
            'order_id': payment.razorpay_order_id,
            'amount': payment.amount_paise,
            'currency': 'INR',
            'status': 'captured',
        }
        get_client.return_value = client

        response = self.client.post(
            reverse('verify_payment'),
            {
                'razorpay_order_id': payment.razorpay_order_id,
                'razorpay_payment_id': 'pay_test_authorized',
                'razorpay_signature': 'valid-test-signature',
            },
        )

        self.assertEqual(response.status_code, 200)
        client.payment.capture.assert_called_once_with(
            'pay_test_authorized',
            10000,
            {'currency': 'INR'},
        )
        payment.refresh_from_db()
        cart.refresh_from_db()
        self.assertEqual(payment.status, RazorpayPayment.Status.PAID)
        self.assertTrue(cart.is_paid)
