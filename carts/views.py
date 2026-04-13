import hmac
import hashlib
import base64
import uuid
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.csrf import csrf_exempt
from store.models import Product, Variation
from .models import Cart, CartItem, Transaction



def _cart_id(request):
    cart = request.session.session_key
    if not cart:
        cart = request.session.create()
    return cart


def generate_esewa_signature(total_amount, transaction_uuid, product_code, secret_key):
    """
    eSewa v2 HMAC-SHA256 Signature Generator
    Order MUST be: total_amount, transaction_uuid, product_code
    """
    parameter_string = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    secret_key_bytes = bytes(secret_key, 'utf-8')
    data_bytes = bytes(parameter_string, 'utf-8')
    hash_result = hmac.new(secret_key_bytes, data_bytes, hashlib.sha256).digest()
    return base64.b64encode(hash_result).decode('utf-8')



def add_cart(request, product_id):
    current_user = request.user
    product = Product.objects.get(id=product_id)

    if current_user.is_authenticated:
        product_variation = []
        if request.method == 'POST':
            for item in request.POST:
                key = item
                value = request.POST[key]
                try:
                    variation = Variation.objects.get(
                        product=product,
                        variation_category__iexact=key,
                        variation_value__iexact=value
                    )
                    product_variation.append(variation)
                except:
                    pass

        is_cart_item_exists = CartItem.objects.filter(product=product, user=current_user).exists()
        if is_cart_item_exists:
            cart_item = CartItem.objects.filter(product=product, user=current_user)
            ex_var_list = []
            id = []
            for item in cart_item:
                existing_variation = item.variations.all()
                ex_var_list.append(list(existing_variation))
                id.append(item.id)

            if product_variation in ex_var_list:
                index = ex_var_list.index(product_variation)
                item_id = id[index]
                item = CartItem.objects.get(product=product, id=item_id)
                item.quantity += 1
                item.save()
            else:
                item = CartItem.objects.create(product=product, quantity=1, user=current_user)
                if len(product_variation) > 0:
                    item.variations.clear()
                    item.variations.add(*product_variation)
                item.save()
        else:
            cart_item = CartItem.objects.create(product=product, quantity=1, user=current_user)
            if len(product_variation) > 0:
                cart_item.variations.clear()
                cart_item.variations.add(*product_variation)
            cart_item.save()
        return redirect('cart')

    else:
        product_variation = []
        if request.method == 'POST':
            for item in request.POST:
                key = item
                value = request.POST[key]
                try:
                    variation = Variation.objects.get(
                        product=product,
                        variation_category__iexact=key,
                        variation_value__iexact=value
                    )
                    product_variation.append(variation)
                except:
                    pass

        try:
            cart = Cart.objects.get(cart_id=_cart_id(request))
        except Cart.DoesNotExist:
            cart = Cart.objects.create(cart_id=_cart_id(request))
        cart.save()

        is_cart_item_exists = CartItem.objects.filter(product=product, cart=cart).exists()
        if is_cart_item_exists:
            cart_item = CartItem.objects.filter(product=product, cart=cart)
            ex_var_list = []
            id = []
            for item in cart_item:
                existing_variation = item.variations.all()
                ex_var_list.append(list(existing_variation))
                id.append(item.id)

            if product_variation in ex_var_list:
                index = ex_var_list.index(product_variation)
                item_id = id[index]
                item = CartItem.objects.get(product=product, id=item_id)
                item.quantity += 1
                item.save()
            else:
                item = CartItem.objects.create(product=product, quantity=1, cart=cart)
                if len(product_variation) > 0:
                    item.variations.clear()
                    item.variations.add(*product_variation)
                item.save()
        else:
            cart_item = CartItem.objects.create(product=product, quantity=1, cart=cart)
            if len(product_variation) > 0:
                cart_item.variations.clear()
                cart_item.variations.add(*product_variation)
            cart_item.save()
        return redirect('cart')


def remove_cart(request, product_id, cart_item_id):
    product = get_object_or_404(Product, id=product_id)
    try:
        if request.user.is_authenticated:
            cart_item = CartItem.objects.get(product=product, user=request.user, id=cart_item_id)
        else:
            cart = Cart.objects.get(cart_id=_cart_id(request))
            cart_item = CartItem.objects.get(product=product, cart=cart, id=cart_item_id)
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
        else:
            cart_item.delete()
    except:
        pass
    return redirect('cart')


def remove_cart_item(request, product_id, cart_item_id):
    product = get_object_or_404(Product, id=product_id)
    if request.user.is_authenticated:
        cart_item = CartItem.objects.get(product=product, user=request.user, id=cart_item_id)
    else:
        cart = Cart.objects.get(cart_id=_cart_id(request))
        cart_item = CartItem.objects.get(product=product, cart=cart, id=cart_item_id)
    cart_item.delete()
    return redirect('cart')


def cart(request, total=0, quantity=0, cart_items=None):
    try:
        tax = 0
        grand_total = 0
        if request.user.is_authenticated:
            cart_items = CartItem.objects.filter(user=request.user, is_active=True)
        else:
            cart = Cart.objects.get(cart_id=_cart_id(request))
            cart_items = CartItem.objects.filter(cart=cart, is_active=True)
        for cart_item in cart_items:
            total += (cart_item.product.price * cart_item.quantity)
            quantity += cart_item.quantity
        tax = (13 * total) / 100
        grand_total = total + tax
    except ObjectDoesNotExist:
        pass

    context = {
        'total': total,
        'quantity': quantity,
        'cart_items': cart_items,
        'tax': tax,
        'grand_total': grand_total,
    }
    return render(request, 'store/cart.html', context)


@login_required(login_url='login')
def checkout(request, total=0, quantity=0, cart_items=None):
    try:
        tax = 0
        grand_total = 0
        if request.user.is_authenticated:
            cart_items = CartItem.objects.filter(user=request.user, is_active=True)
        else:
            cart = Cart.objects.get(cart_id=_cart_id(request))
            cart_items = CartItem.objects.filter(cart=cart, is_active=True)
        for cart_item in cart_items:
            total += (cart_item.product.price * cart_item.quantity)
            quantity += cart_item.quantity
        tax = (13 * total) / 100
        grand_total = total + tax
    except ObjectDoesNotExist:
        pass

    context = {
        'total': total,
        'quantity': quantity,
        'cart_items': cart_items,
        'tax': tax,
        'grand_total': grand_total,
    }
    return render(request, 'store/checkout.html', context)




# eSewa test credentials
ESEWA_PRODUCT_CODE = "EPAYTEST"
ESEWA_SECRET_KEY   = "8gBm/:&EnhH.1/q"
ESEWA_PAYMENT_URL  = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"

@csrf_exempt
@login_required(login_url='login')
def esewa_payment(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart_items = CartItem.objects.filter(user=request.user, is_active=True)

    # ✅ Clean amount — eSewa needs "500" not "500.0"
    total_amount = str(int(float(product.price)))

    # ✅ Generate unique transaction ID
    transaction_uuid = str(uuid.uuid4())

    # ✅ Generate signature
    signature = generate_esewa_signature(
        total_amount,
        transaction_uuid,
        ESEWA_PRODUCT_CODE,
        ESEWA_SECRET_KEY
    )

    # ✅ Debug — check terminal
    print("======= eSewa Debug =======")
    print(f"Product      : {product.product_name}")
    print(f"total_amount : {total_amount}")
    print(f"UUID         : {transaction_uuid}")
    print(f"Signature    : {signature}")
    print("===========================")

    # ✅ Save pending transaction to database
    Transaction.objects.create(
        user=request.user,
        product=product,
        transaction_uuid=transaction_uuid,
        transaction_amount=total_amount,
        tax_amount=0,
        total_amount=total_amount,
        service_charge=0,
        delivery_charge=0,
        transaction_status='pending',
    )

    context = {
        'product': product,
        'cart_items': cart_items,
        'total_amount': total_amount,
        'transaction_uuid': transaction_uuid,
        'product_code': ESEWA_PRODUCT_CODE,
        'signature': signature,
        'esewa_payment_url': ESEWA_PAYMENT_URL,
        'success_url': f"http://127.0.0.1:8000/cart/esewa/success/{transaction_uuid}/",
        'failure_url': f"http://127.0.0.1:8000/cart/esewa/failure/{transaction_uuid}/",
    }
    return render(request, 'orders/payments.html', context)

@csrf_exempt
@login_required(login_url='login')
def esewa_success(request, uid):
    encoded_data = request.GET.get('data')

    if encoded_data:
        try:
            decoded_bytes = base64.b64decode(encoded_data)
            decoded_data = json.loads(decoded_bytes.decode('utf-8'))

            print("eSewa Success Data:", decoded_data)  # debug

            status           = decoded_data.get('status')
            transaction_uuid = decoded_data.get('transaction_uuid')
            total_amount     = decoded_data.get('total_amount')

            if status == 'COMPLETE':
                try:
                    transaction = Transaction.objects.get(transaction_uuid=transaction_uuid)
                    transaction.transaction_status = 'completed'
                    transaction.save()

                    return render(request, 'orders/esewa_success.html', {
                        'transaction_uuid': transaction_uuid,
                        'total_amount': total_amount,
                        'status': status,
                        'product_name': transaction.product.product_name,
                    })
                except Transaction.DoesNotExist:
                    messages.error(request, "Transaction not found.")
                    return redirect('checkout')

        except Exception as e:
            print(f"eSewa Success Error: {e}")
            messages.error(request, f"Payment verification error: {e}")

    return redirect('checkout')


@csrf_exempt
def esewa_failure(request, uid):
    try:
        transaction = Transaction.objects.get(transaction_uuid=uid)
        transaction.transaction_status = 'failed'
        transaction.save()
    except Transaction.DoesNotExist:
        pass

    return render(request, 'orders/esewa_failure.html')