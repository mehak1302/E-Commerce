from csv import list_dialects
from django.contrib import admin

# Register your models here.

from .models import *




@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['category_name', 'slug', 'product_count']
    search_fields = ['category_name']
    readonly_fields = ['slug']

    @admin.display(description='Products')
    def product_count(self, category):
        return category.products.count()

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = [
        'coupon_name',
        'coupon_code',
        'discount_price',
        'minimum_amount',
        'is_expired',
    ]
    list_filter = ['is_expired']
    search_fields = ['coupon_name', 'coupon_code', 'description']
    fieldsets = [
        ('Offer details', {
            'fields': ('coupon_name', 'description', 'coupon_code'),
        }),
        ('Discount rules', {
            'fields': ('discount_price', 'minimum_amount', 'is_expired'),
        }),
    ]

class ProductImageAdmin(admin.StackedInline):
    model =ProductImage

class ProductAdmin(admin.ModelAdmin):
    list_display = ['product_name' , 'price' ]
    inlines = [ProductImageAdmin]


@admin.register(ColorVariant)
class ColorVariantAdmin(admin.ModelAdmin):
    list_display = ['color_name' , 'price']
    model = ColorVariant

@admin.register(SizeVariant)
class SizeVariantAdmin(admin.ModelAdmin):
    list_display = ['size_name' , 'price']

    model = SizeVariant


admin.site.register(Product ,ProductAdmin)


admin.site.register(ProductImage)