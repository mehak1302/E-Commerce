from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product


class HomePageTests(TestCase):
    def test_homepage_shows_categories_and_product_section(self):
        phones = Category.objects.create(
            category_name="Smartphones",
            category_image="catgories/phones.jpg",
        )
        Category.objects.create(category_name="Kitchen")
        Product.objects.create(
            product_name="Test phone",
            category=phones,
            price=12000,
            product_desription="A phone for the home page",
        )

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explore categories")
        self.assertContains(response, "Shop our products")
        self.assertContains(response, "/static/images/home/galaxy-banner.png")
        self.assertContains(response, "Smartphones")
        self.assertContains(response, "1 product")
        self.assertContains(response, "0 products")
        self.assertContains(response, f"?category={phones.slug}#products")
        self.assertContains(response, "/media/catgories/phones.jpg")
        self.assertContains(response, "/static/images/home/furniture.jpg")

    def test_homepage_handles_an_empty_product_catalog(self):
        response = self.client.get(reverse("index"))

        self.assertContains(
            response,
            "Products will appear here as soon as they are added to the store.",
        )

    def test_exact_product_search_redirects_to_product_page(self):
        category = Category.objects.create(category_name="Phones")
        product = Product.objects.create(
            product_name="Test phone",
            category=category,
            price=12000,
            product_desription="A phone for searching",
        )

        response = self.client.get(reverse("index"), {"q": "Test phone"})

        self.assertRedirects(
            response,
            reverse("get_product", args=[product.slug]),
        )

    def test_partial_search_shows_only_matching_products_and_info_sections(self):
        category = Category.objects.create(category_name="Phones")
        matching = Product.objects.create(
            product_name="Blue phone",
            category=category,
            price=12000,
            product_desription="A blue phone",
        )
        second_match = Product.objects.create(
            product_name="Phone case",
            category=category,
            price=500,
            product_desription="Protective case",
        )
        other_category = Category.objects.create(category_name="Lighting")
        Product.objects.create(
            product_name="Desk lamp",
            category=other_category,
            price=2000,
            product_desription="A lamp",
        )

        response = self.client.get(reverse("index"), {"q": "phone"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching.product_name)
        self.assertContains(response, second_match.product_name)
        self.assertNotContains(response, "Desk lamp")
        self.assertContains(response, 'id="delivery"')
        self.assertContains(response, 'id="payment"')

    def test_category_image_opens_only_products_from_that_database_category(self):
        phones = Category.objects.create(
            category_name="Smartphones",
            category_image="catgories/phones.jpg",
        )
        kitchen = Category.objects.create(category_name="Kitchen")
        phone = Product.objects.create(
            product_name="Blue phone",
            category=phones,
            price=12000,
            product_desription="A phone",
        )
        Product.objects.create(
            product_name="Kitchen mixer",
            category=kitchen,
            price=3000,
            product_desription="A mixer",
        )

        response = self.client.get(reverse("index"), {"category": phones.slug})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, phone.product_name)
        self.assertContains(response, phones.category_name)
        self.assertNotContains(response, "Kitchen mixer")
        self.assertContains(response, reverse("index") + "#products")

    def test_unknown_category_shows_a_message_instead_of_all_products(self):
        response = self.client.get(reverse("index"), {"category": "not-a-category"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This category could not be found.")
