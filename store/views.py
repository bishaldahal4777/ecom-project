from django.shortcuts import render, get_object_or_404, redirect
from .models import Product, ReviewRating, ProductGallery
from category.models import Category
from carts.models import CartItem
from carts.views import _cart_id
from django.core.paginator import Paginator
from .forms import ReviewForm
from django.contrib import messages
from orders.models import OrderProduct


def store(request, category_slug=None):
    """
    Price Range Filter Algorithm:
    Step 1 — Read min_price and max_price from the request (URL parameters)
    Step 2 — Start with all available products
    Step 3 — If category selected, narrow down to that category first
    Step 4 — If price range given, filter products that fall within the range
    Step 5 — Sort the filtered results (by price or random)
    Step 6 — Paginate and return
    """
    categories = None
    products = None
 
    # Step 1: Read filter inputs from URL
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    sort_by   = request.GET.get('sort_by', 'random')
 
    # Step 2 & 3: Base queryset
    if category_slug is not None:
        categories = get_object_or_404(Category, slug=category_slug)
        products = Product.objects.filter(
            category=categories,
            is_available=True
        )
    else:
        products = Product.objects.filter(is_available=True)
 
    # Step 4: Apply price range filter
    if min_price != '':
        try:
            products = products.filter(price__gte=int(min_price))
        except ValueError:
            pass
 
    if max_price != '':
        try:
            products = products.filter(price__lte=int(max_price))
        except ValueError:
            pass
 
    # Step 5: Sort
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    else:
        products = products.order_by('?')
 
    # Step 6: Paginate
    paginator = Paginator(products, 3)
    page = request.GET.get('page')
    paged_products = paginator.get_page(page)
    product_count = products.count()
 
    context = {
        'products':      paged_products,
        'product_count': product_count,
        'min_price':     min_price,
        'max_price':     max_price,
        'sort_by':       sort_by,
    }
    return render(request, 'store/store.html', context)


def get_recommendations(product):
    """
    Content-based filtering algorithm:
    - Find products in the same category
    - Score each by price similarity to current product
    - Return top 4 highest scoring products
    """
    same_category = Product.objects.filter(
        category=product.category,
        is_available=True
    ).exclude(id=product.id)

    scored = []
    for p in same_category:
        price_diff = abs(p.price - product.price)
        score = 1 / (1 + price_diff)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for score, p in scored[:4]]


def product_detail(request, category_slug, product_slug):
    try:
        single_product = Product.objects.get(
            category__slug=category_slug,
            slug=product_slug
        )
        in_cart = CartItem.objects.filter(
            cart__cart_id=_cart_id(request),
            product=single_product
        ).exists()
    except Exception as e:
        raise e

    if request.user.is_authenticated:
        try:
            orderproduct = OrderProduct.objects.filter(
                user=request.user,
                product_id=single_product.id
            ).exists()
        except OrderProduct.DoesNotExist:
            orderproduct = None
    else:
        orderproduct = None

    reviews = ReviewRating.objects.filter(
        product_id=single_product.id,
        status=True
    )
    product_gallery = ProductGallery.objects.filter(
        product_id=single_product.id
    )
    recommended = get_recommendations(single_product)

    context = {
        'single_product': single_product,
        'in_cart': in_cart,
        'orderproduct': orderproduct,
        'reviews': reviews,
        'product_gallery': product_gallery,
        'recommended': recommended,
    }
    return render(request, 'store/product_detail.html', context)


def search(request):
    """
    Priority-based search algorithm:
    Step 1 — find products where keyword matches the product name (high relevance)
    Step 2 — find products where keyword only matches the description (lower relevance)
    Step 3 — merge: name matches come first, then description-only matches
    This ensures more relevant results always appear at the top.
    """
    products = []
    product_count = 0
    keyword = request.GET.get('keyword', '').strip()

    if keyword:
        name_matches = Product.objects.filter(
            product_name__icontains=keyword,
            is_available=True
        )
        desc_matches = Product.objects.filter(
            description__icontains=keyword,
            is_available=True
        ).exclude(product_name__icontains=keyword)

        products = list(name_matches) + list(desc_matches)
        product_count = len(products)

    context = {
        'products': products,
        'product_count': product_count,
        'keyword': keyword,
    }
    return render(request, 'store/store.html', context)


def submit_review(request, product_id):
    url = request.META.get('HTTP_REFERER')
    if request.method == 'POST':
        try:
            reviews = ReviewRating.objects.get(
                user__id=request.user.id,
                product__id=product_id
            )
            form = ReviewForm(request.POST, instance=reviews)
            form.save()
            messages.success(request, 'Thank you! Your review has been updated.')
            return redirect(url)
        except ReviewRating.DoesNotExist:
            form = ReviewForm(request.POST)
            if form.is_valid():
                data = ReviewRating()
                data.subject = form.cleaned_data['subject']
                data.rating = form.cleaned_data['rating']
                data.review = form.cleaned_data['review']
                data.ip = request.META.get('REMOTE_ADDR')
                data.product_id = product_id
                data.user_id = request.user.id
                data.save()
                messages.success(request, 'Thank you! Your review has been submitted.')
                return redirect(url)