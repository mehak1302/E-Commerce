from django.shortcuts import get_object_or_404, render
from products.models import Product

def get_product(request, slug):
    product = get_object_or_404(Product, slug=slug)
    context = {
        'product': product,
        'sizes': product.size_variant.all(),
        'colors': product.color_variant.all(),
    }

    size = request.GET.get('size')
    if size:
        size_variant = product.size_variant.filter(size_name=size).first()
        if size_variant:
            context['selected_size'] = size
            context['updated_price'] = product.get_product_price_by_size(size_variant)

    return render(request, 'product/product.html', context=context)