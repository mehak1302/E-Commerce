from django.db.models import Count, Q
from django.shortcuts import redirect, render
from products.models import Category, Product

# Create your views here.

def index(request):
    query = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category', '').strip()
    selected_category = Category.objects.filter(slug=category_slug).first()
    products = Product.objects.all()

    if category_slug:
        if selected_category:
            products = products.filter(category=selected_category)
        else:
            products = products.none()

    if query:
        products = products.filter(
            Q(product_name__icontains=query)
            | Q(product_desription__icontains=query)
            | Q(category__category_name__icontains=query)
        ).distinct()

        if products.count() == 1 and not category_slug:
            return redirect('get_product', slug=products.first().slug)

    return render(request, 'home/index.html', {
        'products': products,
        'categories': Category.objects.annotate(
            product_count=Count('products')
        ).order_by('category_name'),
        'selected_category': selected_category,
        'category_filter_invalid': bool(category_slug) and selected_category is None,
        'search_query': query,
        'is_search': bool(query),
    })