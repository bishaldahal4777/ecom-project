import json
from django.http import JsonResponse


def autocomplete(request):
    """
    Autocomplete algorithm:
    - Get the partial keyword typed by the user
    - Search product names that START WITH the keyword (fastest, most relevant)
    - Also search product names that CONTAIN the keyword (broader matches)
    - Merge them: startswith results come first, then contains-only results
    - Return top 6 suggestions as JSON
    """
    keyword = request.GET.get('term', '').strip()

    if not keyword:
        return JsonResponse([], safe=False)

    # High priority: product name starts with the keyword (e.g. "sh" → "Shoes")
    starts_with = Product.objects.filter(
        product_name__istartswith=keyword,
        is_available=True
    ).values_list('product_name', flat=True)[:6]

    # Lower priority: name contains keyword but doesn't start with it (e.g. "sh" → "Fashion Shirt")
    contains = Product.objects.filter(
        product_name__icontains=keyword,
        is_available=True
    ).exclude(
        product_name__istartswith=keyword
    ).values_list('product_name', flat=True)[:6]

    # Merge and remove duplicates, cap at 6 total
    suggestions = list(dict.fromkeys(list(starts_with) + list(contains)))[:6]

    return JsonResponse(suggestions, safe=False)