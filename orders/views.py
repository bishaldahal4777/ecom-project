from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from carts.models import CartItem
from .forms import OrderForm
from .models import Order, Payment, OrderProduct
from store.models import Product
import datetime
import json
import hmac
import hashlib
import base64
import uuid


# ==============================
# eSewa Configuration
# ==============================
ESEWA_PRODUCT_CODE = "EPAYTEST"
ESEWA_SECRET_KEY   = "8gBm/:&EnhH.1/q"
ESEWA_PAYMENT_URL  = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"


def generate_esewa_signature(total_amount, transaction_uuid, product_code, secret_key):
    """eSewa v2 HMAC-SHA256 Signature — order MUST be: total_amount, transaction_uuid, product_code"""
    parameter_string = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    hash_result = hmac.new(
        bytes(secret_key, 'utf-8'),
        bytes(parameter_string, 'utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(hash_result).decode('utf-8')


# ==============================
# PayPal / Generic Payment View
# ==============================
def payments(request):
    body = json.loads(request.body)
    order = Order.objects.get(
        user=request.user,
        is_ordered=False,
        order_number=body['orderID']
    )

    payment = Payment(
        user=request.user,
        payment_id=body['transID'],
        payment_method=body['payment_method'],
        amount_paid=order.order_total,
        status=body['status'],
    )
    payment.save()

    order.payment = payment
    order.is_ordered = True
    order.save()

    cart_items = CartItem.objects.filter(user=request.user)
    for item in cart_items:
        orderproduct = OrderProduct()
        orderproduct.order_id = order.id
        orderproduct.payment = payment
        orderproduct.user_id = request.user.id
        orderproduct.product_id = item.product_id
        orderproduct.quantity = item.quantity
        orderproduct.product_price = item.product.price
        orderproduct.ordered = True
        orderproduct.save()

        cart_item = CartItem.objects.get(id=item.id)
        product_variation = cart_item.variations.all()
        orderproduct = OrderProduct.objects.get(id=orderproduct.id)
        orderproduct.variations.set(product_variation)
        orderproduct.save()

        product = Product.objects.get(id=item.product_id)
        product.stock -= item.quantity
        product.save()

    CartItem.objects.filter(user=request.user).delete()

    mail_subject = 'Thank you for your order!'
    message = render_to_string('orders/order_recieved_email.html', {
        'user': request.user,
        'order': order,
    })
    send_email = EmailMessage(mail_subject, message, to=[request.user.email])
    send_email.send()

    data = {
        'order_number': order.order_number,
        'transID': payment.payment_id,
    }
    return JsonResponse(data)


# ==============================
# Place Order + Render eSewa Form
# ==============================
def place_order(request, total=0, quantity=0):
    current_user = request.user

    cart_items = CartItem.objects.filter(user=current_user)
    if cart_items.count() <= 0:
        return redirect('store')

    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity
    tax = (13 * total) / 100
    grand_total = total + tax

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            # Save order
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.country = form.cleaned_data['country']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')
            data.save()

            # Generate order number
            current_date = datetime.date.today().strftime("%Y%m%d")
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            order = Order.objects.get(
                user=current_user,
                is_ordered=False,
                order_number=order_number
            )

            # ✅ Generate eSewa payment fields
            total_amount_str = str(int(grand_total)) if grand_total == int(grand_total) else f"{grand_total:.2f}"
            transaction_uuid = str(uuid.uuid4())
            signature = generate_esewa_signature(
                total_amount_str,
                transaction_uuid,
                ESEWA_PRODUCT_CODE,
                ESEWA_SECRET_KEY
            )

            print("======= eSewa Debug =======")
            print(f"Order Number     : {order_number}")
            print(f"total_amount     : {total_amount_str}")
            print(f"transaction_uuid : {transaction_uuid}")
            print(f"signature        : {signature}")
            print("===========================")

            context = {
                'order': order,
                'cart_items': cart_items,
                'total': total,
                'tax': tax,
                'grand_total': grand_total,
                # ✅ eSewa fields
                'total_amount': total_amount_str,
                'transaction_uuid': transaction_uuid,
                'product_code': ESEWA_PRODUCT_CODE,
                'signature': signature,
                'esewa_payment_url': ESEWA_PAYMENT_URL,
                'success_url': f"http://127.0.0.1:8000/orders/esewa/success/?order_number={order_number}",
                'failure_url': f"http://127.0.0.1:8000/orders/esewa/failure/",
            }
            return render(request, 'orders/payments.html', context)

    return redirect('checkout')


# ==============================
# eSewa Success Callback
# ==============================
def esewa_success(request):
    encoded_data = request.GET.get('data')
    order_number = request.GET.get('order_number')

    if not encoded_data:
        return redirect('checkout')

    try:
        decoded_bytes = base64.b64decode(encoded_data)
        decoded_data = json.loads(decoded_bytes.decode('utf-8'))

        print("eSewa Success Data:", decoded_data)

        status           = decoded_data.get('status')
        transaction_uuid = decoded_data.get('transaction_uuid')
        total_amount     = decoded_data.get('total_amount')

        if status != 'COMPLETE':
            return redirect('checkout')

        order = Order.objects.get(order_number=order_number)

        # Save payment
        payment = Payment.objects.create(
            user=request.user,
            payment_id=transaction_uuid,
            payment_method='eSewa',
            amount_paid=total_amount,
            status='COMPLETED',
        )

        order.payment = payment
        order.is_ordered = True
        order.save()

        # Move cart items to OrderProduct
        cart_items = CartItem.objects.filter(user=request.user)
        for item in cart_items:
            orderproduct = OrderProduct()
            orderproduct.order_id = order.id
            orderproduct.payment = payment
            orderproduct.user_id = request.user.id
            orderproduct.product_id = item.product_id
            orderproduct.quantity = item.quantity
            orderproduct.product_price = item.product.price
            orderproduct.ordered = True
            orderproduct.save()

            cart_item = CartItem.objects.get(id=item.id)
            product_variation = cart_item.variations.all()
            orderproduct = OrderProduct.objects.get(id=orderproduct.id)
            orderproduct.variations.set(product_variation)
            orderproduct.save()

            # Reduce stock
            product = Product.objects.get(id=item.product_id)
            product.stock -= item.quantity
            product.save()

        # Clear cart
        CartItem.objects.filter(user=request.user).delete()

        return redirect(
            f'/orders/order_complete/?order_number={order.order_number}&payment_id={payment.payment_id}'
        )

    except Exception as e:
        print(f"eSewa success error: {e}")
        return redirect('checkout')


# ==============================
# eSewa Failure Callback
# ==============================
def esewa_failure(request):
    return redirect('checkout')


# ==============================
# Order Complete
# ==============================
def order_complete(request):
    order_number = request.GET.get('order_number')
    transID = request.GET.get('payment_id')

    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        ordered_products = OrderProduct.objects.filter(order_id=order.id)

        subtotal = 0
        for i in ordered_products:
            subtotal += i.product_price * i.quantity

        payment = Payment.objects.get(payment_id=transID)

        context = {
            'order': order,
            'ordered_products': ordered_products,
            'order_number': order.order_number,
            'transID': payment.payment_id,
            'payment': payment,
            'subtotal': subtotal,
        }
        return render(request, 'orders/order_complete.html', context)
    except (Payment.DoesNotExist, Order.DoesNotExist):
        return redirect('home')