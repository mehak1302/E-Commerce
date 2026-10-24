from django.test import TestCase

# Create your tests here.
from django.test import TestCase
from django.urls import reverse

from products.models import Category, ColorVariant, Product, SizeVariant


class ProductSizePriceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(category_name="Test category")
        self.product = Product.objects.create(
            product_name="Test product",
            category=self.category,
            price=100,
            product_desription="Test description",
        )
        self.large_size = SizeVariant.objects.create(size_name="Large", price=25)
        self.product.size_variant.add(self.large_size)
        self.red_color = ColorVariant.objects.create(color_name="Red", price=10)
        self.product.color_variant.add(self.red_color)

    def test_selecting_size_keeps_product_and_updates_price(self):
        response = self.client.get(
            reverse("get_product", args=[self.product.slug]),
            {"size": self.large_size.size_name},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.product_name)
        self.assertContains(response, "₹125.00")
        self.assertContains(response, 'value="Large"')
        self.assertContains(response, "checked")
        self.assertContains(response, 'name="color_variant"')
        self.assertContains(response, "Red")
        self.assertContains(response, 'data-quantity-change="1"')
        self.assertContains(response, 'name="buy_now"')
        self.assertContains(response, "product-thumbnail")

    def test_size_not_belonging_to_product_does_not_hide_product(self):
        SizeVariant.objects.create(size_name="Unavailable", price=50)

        response = self.client.get(
            reverse("get_product", args=[self.product.slug]),
            {"size": "Unavailable"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.product_name)
        self.assertContains(response, "₹100.00")
