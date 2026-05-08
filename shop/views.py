import datetime
import json
from decimal import Decimal, InvalidOperation
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db.models import ProtectedError, Q, Count, Sum, F, ExpressionWrapper, DecimalField, Max
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.utils.text import slugify
from .models import Product, Category, Color, Order, OrderItem, Inventory, Wishlist, Address, UserProfile, ProductImage, PackagingOption, GlobalPackagingOption, Banner
from .cart import Cart, FREE_DELIVERY_THRESHOLD, DELIVERY_COST


def index(request):
    products = Product.objects.filter(is_available=True)[:8]
    categories = Category.objects.all()[:6]
    banner = Banner.get_active()
    return render(request, 'shop/index.html', {'products': products, 'categories': categories, 'banner': banner})


def _page_range(page_obj):
    current = page_obj.number
    total = page_obj.paginator.num_pages
    if total <= 7:
        return list(range(1, total + 1))
    pages = [1]
    left = max(2, current - 2)
    right = min(total - 1, current + 2)
    if left > 2:
        pages.append(None)
    pages.extend(range(left, right + 1))
    if right < total - 1:
        pages.append(None)
    pages.append(total)
    return pages


def catalog(request):
    products = Product.objects.filter(is_available=True).select_related('category')

    category_slug = request.GET.get('category', '')
    price_min = request.GET.get('price_min', '')
    price_max = request.GET.get('price_max', '')
    sort = request.GET.get('sort', 'created_at')
    q = request.GET.get('q', '').strip()
    color_slugs = request.GET.getlist('colors')

    if category_slug:
        products = products.filter(category__slug=category_slug)
    if price_min:
        products = products.filter(price__gte=price_min)
    if price_max:
        products = products.filter(price__lte=price_max)
    if color_slugs:
        products = products.filter(colors__slug__in=color_slugs).distinct()

    sort_map = {
        'price-asc': 'price',
        'price-desc': '-price',
        'new': '-created_at',
    }
    products = products.order_by(sort_map.get(sort, '-created_at'))

    if q:
        q_lower = q.lower()
        products = [
            p for p in products
            if q_lower in p.name.lower() or q_lower in p.description.lower()
        ]

    total_count = len(products) if isinstance(products, list) else products.count()

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)
    filter_params = params.urlencode()

    categories = Category.objects.all()
    colors = Color.objects.all()

    wishlist_ids = set(
        Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
    ) if request.user.is_authenticated else set()

    return render(request, 'shop/catalog.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'page_range': _page_range(page_obj),
        'filter_params': filter_params,
        'total_count': total_count,
        'categories': categories,
        'current_category': category_slug,
        'price_min': price_min,
        'price_max': price_max,
        'sort': sort,
        'q': q,
        'wishlist_ids': wishlist_ids,
        'colors': colors,
        'current_colors': color_slugs,
    })


def product(request, slug):
    item = get_object_or_404(Product, slug=slug, is_available=True)
    related = Product.objects.filter(
        category=item.category, is_available=True
    ).exclude(pk=item.pk)[:4]
    try:
        stock = item.inventory.quantity
    except Exception:
        stock = None

    if stock is None:
        stock_status = 'unknown'
    elif stock == 0:
        stock_status = 'none'
    elif stock < 5:
        stock_status = 'low'
    else:
        stock_status = 'ok'

    in_wishlist = (
        request.user.is_authenticated and
        Wishlist.objects.filter(user=request.user, product=item).exists()
    )

    gallery_images = []
    if item.image:
        gallery_images.append({'url': item.image.url, 'pk': None})
    for img in item.images.all():
        gallery_images.append({'url': img.image.url, 'pk': img.pk})

    packaging_options = list(item.packaging_options.values('id', 'name', 'price_modifier'))
    if not packaging_options:
        packaging_options = list(GlobalPackagingOption.objects.values('id', 'name', 'price_modifier'))
        if not packaging_options:
            packaging_options = [
                {'id': None, 'name': 'Крафт', 'price_modifier': 0},
                {'id': None, 'name': 'Фатин', 'price_modifier': 0},
                {'id': None, 'name': 'Шляпная коробка', 'price_modifier': 0},
            ]

    return render(request, 'shop/product.html', {
        'product': item,
        'related': related,
        'stock': stock,
        'stock_status': stock_status,
        'in_wishlist': in_wishlist,
        'gallery_images': gallery_images,
        'packaging_options': packaging_options,
    })


def cart(request):
    c = Cart(request)
    subtotal = c.get_total_price()
    delivery = c.get_delivery()
    total = subtotal + delivery
    free_delivery_left = max(Decimal('0'), FREE_DELIVERY_THRESHOLD - subtotal)
    delivery_progress = min(100, int(subtotal / FREE_DELIVERY_THRESHOLD * 100))
    cart_ids = list(c.cart.keys())
    suggestions = Product.objects.filter(is_available=True).exclude(pk__in=cart_ids)[:5]
    return render(request, 'shop/cart.html', {
        'cart': c,
        'subtotal': subtotal,
        'delivery': delivery,
        'total': total,
        'free_delivery_left': free_delivery_left,
        'delivery_progress': delivery_progress,
        'suggestions': suggestions,
    })


def cart_add(request, product_id):
    if request.method != 'POST':
        return redirect('cart')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    c = Cart(request)
    product = get_object_or_404(Product, pk=product_id, is_available=True)
    try:
        quantity = max(1, int(request.POST.get('quantity', 1)))
    except (ValueError, TypeError):
        quantity = 1

    try:
        stock = product.inventory.quantity
    except Inventory.DoesNotExist:
        stock = None

    if stock is not None:
        current = c.cart.get(str(product_id), {}).get('quantity', 0)
        if stock == 0 or current >= stock:
            msg = 'Товар закончился' if stock == 0 else f'В корзине максимум ({stock} шт.)'
            if is_ajax:
                return JsonResponse({'ok': False, 'error': msg})
            return redirect('cart')
        quantity = min(quantity, stock - current)

    packaging = request.POST.get('packaging', '').strip()
    ribbon = request.POST.get('ribbon', '').strip()

    final_price = product.price
    db_option = PackagingOption.objects.filter(product=product, name=packaging).first()
    if db_option:
        final_price += db_option.price_modifier
    elif packaging and not product.packaging_options.exists():
        global_opt = GlobalPackagingOption.objects.filter(name=packaging).first()
        if global_opt:
            final_price += global_opt.price_modifier

    extras_parts = []
    if packaging:
        extras_parts.append(f'Упаковка: {packaging}')
    if ribbon:
        extras_parts.append(f'Лента: {ribbon}')
    extras = ', '.join(extras_parts)

    c.add(product, quantity, extras=extras, price=final_price)
    if is_ajax:
        return JsonResponse({'ok': True, 'count': len(c)})
    return redirect('cart')


def cart_remove(request, product_id):
    if request.method == 'POST':
        c = Cart(request)
        product = get_object_or_404(Product, pk=product_id)
        c.remove(product)
    return redirect('cart')


def cart_update(request, product_id):
    if request.method == 'POST':
        c = Cart(request)
        product = get_object_or_404(Product, pk=product_id)
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (ValueError, TypeError):
            quantity = 1
        try:
            stock = product.inventory.quantity
            quantity = min(quantity, stock)
        except Inventory.DoesNotExist:
            pass
        c.add(product, quantity, override=True)
    return redirect('cart')


def cart_clear(request):
    if request.method == 'POST':
        Cart(request).clear()
    return redirect('cart')


def account(request):
    if not request.user.is_authenticated:
        return redirect(f'/auth/?next=/account/')
    orders = request.user.orders.order_by('-created_at').prefetch_related('items__product')
    wishlist = request.user.wishlist.select_related('product').order_by('-created_at')
    addresses = request.user.addresses.all()
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'shop/account.html', {
        'orders': orders,
        'wishlist': wishlist,
        'addresses': addresses,
        'profile': profile,
    })


def checkout(request):
    c = Cart(request)
    if not c:
        return redirect('cart')

    if request.method == 'POST':
        fname = request.POST.get('fname', '').strip()
        lname = request.POST.get('lname', '').strip()
        name = f'{fname} {lname}'.strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        receive = request.POST.get('receive', 'delivery')

        if receive == 'pickup':
            address = 'Самовывоз: г. Омск, ул. Ленина, 12'
        else:
            street = request.POST.get('street', '').strip()
            house = request.POST.get('house', '').strip()
            flat = request.POST.get('flat', '').strip()
            entrance = request.POST.get('entrance', '').strip()
            address = f'ул. {street}, д. {house}'
            if flat:
                address += f', кв. {flat}'
            if entrance:
                address += f', подъезд/этаж {entrance}'

        date = request.POST.get('date', '')
        time_slot = request.POST.get('time_slot', '')
        asap = request.POST.get('asap') == 'on'
        payment = request.POST.get('payment', 'online')
        courier_note = request.POST.get('courier_note', '').strip()
        card_text = request.POST.get('card_text', '').strip()
        card_from = request.POST.get('card_from', '').strip()

        comment_parts = []
        if asap:
            comment_parts.append(f'Доставка: как можно скорее ({date})')
        elif date and time_slot:
            comment_parts.append(f'Доставка: {date}, {time_slot}')
        payment_labels = {'online': 'Картой онлайн', 'cash': 'Наличными курьеру', 'sbp': 'СБП'}
        comment_parts.append(f'Оплата: {payment_labels.get(payment, payment)}')
        if email:
            comment_parts.append(f'Email: {email}')
        if card_text:
            comment_parts.append(f'Открытка: «{card_text}»' + (f' — от {card_from}' if card_from else ''))
        if courier_note:
            comment_parts.append(f'Курьеру: {courier_note}')

        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=name,
            phone=phone,
            address=address,
            comment='\n'.join(comment_parts),
            total_price=c.get_total(),
        )
        for item in c:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                price=item['price'],
                extras=item.get('extras', ''),
            )
            try:
                inv = item['product'].inventory
                inv.quantity = max(0, inv.quantity - item['quantity'])
                inv.save(update_fields=['quantity'])
            except Inventory.DoesNotExist:
                pass
        c.clear()
        request.session['last_order_id'] = order.pk
        return redirect('order_success')

    subtotal = c.get_total_price()
    delivery = c.get_delivery()
    total = c.get_total()
    default_address = None
    user_profile = None
    if request.user.is_authenticated:
        default_address = Address.objects.filter(user=request.user, is_default=True).first() or \
                          Address.objects.filter(user=request.user).first()
        user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'shop/checkout.html', {
        'cart': c,
        'subtotal': subtotal,
        'delivery': delivery,
        'total': total,
        'default_address': default_address,
        'user_profile': user_profile,
    })


def order_success(request):
    order_id = request.session.pop('last_order_id', None)
    if not order_id:
        return redirect('index')
    order = get_object_or_404(Order, pk=order_id)
    return render(request, 'shop/order_success.html', {'order': order})


def auth(request):
    from django.contrib.auth.forms import AuthenticationForm
    return render(request, 'shop/auth.html', {
        'form': AuthenticationForm(),
        'next': request.GET.get('next', ''),
    })


_MONTHS_RU = ['январь','февраль','март','апрель','май','июнь',
               'июль','август','сентябрь','октябрь','ноябрь','декабрь']
_DAYS_SHORT = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']


def _pct_delta(new, old):
    if not old:
        return None
    return round((new - old) / old * 100)


def admin_panel(request):
    if not request.user.is_staff:
        return redirect('index')

    now = timezone.now()
    today = now.date()

    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = this_month_start - datetime.timedelta(seconds=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    paid = Order.objects.exclude(status='cancelled')

    this_rev = paid.filter(created_at__gte=this_month_start).aggregate(t=Sum('total_price'))['t'] or Decimal('0')
    last_rev = paid.filter(created_at__gte=last_month_start, created_at__lt=this_month_start).aggregate(t=Sum('total_price'))['t'] or Decimal('0')
    this_cnt = paid.filter(created_at__gte=this_month_start).count()
    last_cnt = paid.filter(created_at__gte=last_month_start, created_at__lt=this_month_start).count()

    seven_ago = datetime.datetime.combine(today - datetime.timedelta(days=6), datetime.time.min)
    seven_ago = timezone.make_aware(seven_ago)

    daily = (
        paid.filter(created_at__gte=seven_ago)
        .annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(total=Sum('total_price'))
        .order_by('day')
    )
    daily_map = {e['day'].date(): float(e['total']) for e in daily}
    chart_days = [today - datetime.timedelta(days=6 - i) for i in range(7)]
    chart_labels = json.dumps([_DAYS_SHORT[d.weekday()] + ' ' + d.strftime('%d.%m') for d in chart_days])
    chart_values = json.dumps([daily_map.get(d, 0) for d in chart_days])

    context = {
        'colors': Color.objects.all(),
        'products': Product.objects.select_related('category', 'inventory').all(),
        'product_count': Product.objects.count(),
        'available_count': Product.objects.filter(is_available=True).count(),
        'new_orders_count': Order.objects.filter(status='new').count(),
        'recent_orders': Order.objects.order_by('-created_at')[:5],
        'all_orders': Order.objects.order_by('-created_at'),
        'status_choices': Order.STATUS_CHOICES,
        'categories': Category.objects.annotate(product_count=Count('products')).order_by('order', 'name'),
        'this_rev': this_rev,
        'last_rev': last_rev,
        'this_cnt': this_cnt,
        'last_cnt': last_cnt,
        'rev_delta': _pct_delta(this_rev, last_rev),
        'cnt_delta': _pct_delta(this_cnt, last_cnt),
        'rev_negative': (_pct_delta(this_rev, last_rev) or 0) < 0,
        'cnt_negative': (_pct_delta(this_cnt, last_cnt) or 0) < 0,
        'current_month': _MONTHS_RU[now.month - 1],
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'max_order_id': Order.objects.aggregate(m=Max('pk'))['m'] or 0,
    }
    return render(request, 'shop/admin_panel.html', context)


def product_detail_json(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    p = get_object_or_404(Product, pk=pk)
    try:
        quantity = p.inventory.quantity
    except Inventory.DoesNotExist:
        quantity = 0
    gallery = [{'id': img.pk, 'url': img.image.url} for img in p.images.all()]
    packaging = [
        {'id': opt.pk, 'name': opt.name, 'price_modifier': str(opt.price_modifier)}
        for opt in p.packaging_options.all()
    ]
    return JsonResponse({
        'id': p.pk,
        'name': p.name,
        'slug': p.slug,
        'category': p.category.pk if p.category else '',
        'description': p.description,
        'price': str(p.price),
        'is_available': p.is_available,
        'quantity': quantity,
        'image_url': p.image.url if p.image else '',
        'gallery': gallery,
        'packaging': packaging,
        'color_ids': list(p.colors.values_list('pk', flat=True)),
    })


def product_save(request, pk=None):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    p = get_object_or_404(Product, pk=pk) if pk else Product()

    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Название обязательно'}, status=400)

    try:
        price = Decimal(request.POST.get('price', '0'))
    except InvalidOperation:
        return JsonResponse({'error': 'Неверная цена'}, status=400)

    p.name = name
    p.price = price
    p.description = request.POST.get('description', '').strip()
    p.is_available = request.POST.get('is_available') == 'on'

    cat_id = request.POST.get('category', '')
    p.category = Category.objects.filter(pk=cat_id).first() if cat_id else None

    raw_slug = request.POST.get('slug', '').strip() or slugify(name)
    base_slug = raw_slug
    counter = 1
    while Product.objects.filter(slug=raw_slug).exclude(pk=p.pk or 0).exists():
        raw_slug = f'{base_slug}-{counter}'
        counter += 1
    p.slug = raw_slug

    if 'image' in request.FILES:
        p.image = request.FILES['image']

    p.save()

    qty = request.POST.get('quantity', '').strip()
    if qty.isdigit():
        Inventory.objects.update_or_create(product=p, defaults={'quantity': int(qty)})

    color_ids = request.POST.getlist('colors')
    p.colors.set(Color.objects.filter(pk__in=color_ids))

    return JsonResponse({'ok': True, 'id': p.pk, 'name': p.name})


def product_delete(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    p = get_object_or_404(Product, pk=pk)
    try:
        p.delete()
    except ProtectedError:
        return JsonResponse({'error': 'Нельзя удалить товар — он есть в заказах'}, status=400)
    return JsonResponse({'ok': True})


def order_detail_json(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    order = get_object_or_404(Order, pk=pk)
    items = [
        {
            'name': item.product.name,
            'quantity': item.quantity,
            'price': str(item.price),
            'subtotal': str(item.subtotal()),
            'extras': item.extras,
        }
        for item in order.items.select_related('product').all()
    ]
    return JsonResponse({
        'id': order.pk,
        'name': order.name,
        'phone': order.phone,
        'address': order.address,
        'comment': order.comment,
        'status': order.status,
        'status_display': order.get_status_display(),
        'total_price': str(order.total_price),
        'created_at': order.created_at.strftime('%d.%m.%Y %H:%M'),
        'items': items,
    })


def order_set_status(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get('status', '')
    valid = [s[0] for s in Order.STATUS_CHOICES]
    if new_status not in valid:
        return JsonResponse({'error': 'invalid status'}, status=400)
    order.status = new_status
    order.save(update_fields=['status'])
    return JsonResponse({'ok': True, 'status': new_status, 'status_display': order.get_status_display()})


def register(request):
    from django.contrib.auth.forms import AuthenticationForm
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        errors = {}
        if not first_name:
            errors['first_name'] = 'Введите имя'
        if not email:
            errors['email'] = 'Введите email'
        elif User.objects.filter(username=email).exists():
            errors['email'] = 'Пользователь с таким email уже зарегистрирован'
        if not password1:
            errors['password1'] = 'Введите пароль'
        elif len(password1) < 8:
            errors['password1'] = 'Пароль должен содержать не менее 8 символов'
        elif password1 != password2:
            errors['password2'] = 'Пароли не совпадают'
        if not errors:
            user = User.objects.create_user(username=email, email=email, password=password1, first_name=first_name)
            login(request, user)
            return redirect('account')
        return render(request, 'shop/auth.html', {
            'form': AuthenticationForm(),
            'reg_errors': errors,
            'reg_data': {'first_name': first_name, 'email': email},
            'active_tab': 'register',
        })
    return redirect('auth')


def packaging_option_save(request, product_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    p = get_object_or_404(Product, pk=product_id)
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Название обязательно'}, status=400)
    try:
        modifier = Decimal(request.POST.get('price_modifier', '0'))
    except InvalidOperation:
        return JsonResponse({'error': 'Неверная надбавка'}, status=400)
    opt = PackagingOption.objects.create(product=p, name=name, price_modifier=modifier)
    return JsonResponse({'ok': True, 'id': opt.pk, 'name': opt.name, 'price_modifier': str(opt.price_modifier)})


def packaging_option_delete(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    opt = get_object_or_404(PackagingOption, pk=pk)
    opt.delete()
    return JsonResponse({'ok': True})


def product_image_add(request, product_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    p = get_object_or_404(Product, pk=product_id)
    if 'image' not in request.FILES:
        return JsonResponse({'error': 'Файл не передан'}, status=400)
    img = ProductImage.objects.create(product=p, image=request.FILES['image'])
    return JsonResponse({'ok': True, 'id': img.pk, 'url': img.image.url})


def product_image_delete(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    img = get_object_or_404(ProductImage, pk=pk)
    img.image.delete(save=False)
    img.delete()
    return JsonResponse({'ok': True})


def orders_export_csv(request):
    import csv
    from django.http import HttpResponse
    if not request.user.is_staff:
        return redirect('index')
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['№', 'Клиент', 'Телефон', 'Адрес', 'Комментарий', 'Сумма', 'Статус', 'Дата'])
    for order in Order.objects.order_by('-created_at'):
        writer.writerow([
            order.pk,
            order.name,
            order.phone,
            order.address,
            order.comment,
            order.total_price,
            order.get_status_display(),
            order.created_at.strftime('%d.%m.%Y %H:%M'),
        ])
    return response


def category_detail_json(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    cat = get_object_or_404(Category, pk=pk)
    return JsonResponse({
        'id': cat.pk,
        'name': cat.name,
        'slug': cat.slug,
        'order': cat.order,
    })


def category_save(request, pk=None):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    cat = get_object_or_404(Category, pk=pk) if pk else Category()

    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Название обязательно'}, status=400)

    raw_slug = request.POST.get('slug', '').strip() or slugify(name)
    base_slug = raw_slug
    counter = 1
    while Category.objects.filter(slug=raw_slug).exclude(pk=cat.pk or 0).exists():
        raw_slug = f'{base_slug}-{counter}'
        counter += 1

    try:
        order = int(request.POST.get('order', 0))
    except (ValueError, TypeError):
        order = 0

    cat.name = name
    cat.slug = raw_slug
    cat.order = order
    cat.save()

    return JsonResponse({
        'ok': True,
        'id': cat.pk,
        'name': cat.name,
        'slug': cat.slug,
        'order': cat.order,
        'product_count': cat.products.count(),
    })


def category_delete(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    cat = get_object_or_404(Category, pk=pk)
    cat.delete()
    return JsonResponse({'ok': True})


def wishlist_toggle(request, product_id):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'auth'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    product = get_object_or_404(Product, pk=product_id)
    obj, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if not created:
        obj.delete()
        action = 'removed'
    else:
        action = 'added'
    count = request.user.wishlist.count()
    return JsonResponse({'ok': True, 'action': action, 'count': count})


def _parse_date_range(request):
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    status = request.GET.get('status', '').strip()
    orders = Order.objects.all()
    try:
        if date_from:
            orders = orders.filter(created_at__gte=timezone.make_aware(datetime.datetime.strptime(date_from, '%Y-%m-%d')))
        if date_to:
            dt_to = datetime.datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            orders = orders.filter(created_at__lte=timezone.make_aware(dt_to))
    except ValueError:
        pass
    if status:
        orders = orders.filter(status=status)
    return orders


def reports_data(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)

    orders = _parse_date_range(request)
    total_count = orders.count()
    total_revenue = orders.exclude(status='cancelled').aggregate(t=Sum('total_price'))['t'] or Decimal('0')
    avg_order = (total_revenue / total_count).quantize(Decimal('1')) if total_count else Decimal('0')

    by_status = []
    for val, label in Order.STATUS_CHOICES:
        qs = orders.filter(status=val)
        cnt = qs.count()
        rev = qs.aggregate(t=Sum('total_price'))['t'] or Decimal('0')
        by_status.append({'status': val, 'label': label, 'count': cnt, 'revenue': str(rev)})

    subtotal_expr = ExpressionWrapper(F('price') * F('quantity'), output_field=DecimalField(max_digits=12, decimal_places=2))
    top_products = (
        OrderItem.objects.filter(order__in=orders)
        .values('product__name')
        .annotate(total_qty=Sum('quantity'), total_sum=Sum(subtotal_expr))
        .order_by('-total_qty')[:10]
    )

    return JsonResponse({
        'total_count': total_count,
        'total_revenue': str(total_revenue),
        'avg_order': str(avg_order),
        'by_status': by_status,
        'top_products': [
            {'name': p['product__name'], 'qty': p['total_qty'], 'sum': str(p['total_sum'] or 0)}
            for p in top_products
        ],
    })


def reports_sales(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)

    orders = _parse_date_range(request).exclude(status='cancelled')
    total_count = orders.count()
    total_revenue = orders.aggregate(t=Sum('total_price'))['t'] or Decimal('0')
    avg_order = (total_revenue / total_count).quantize(Decimal('1')) if total_count else Decimal('0')

    subtotal_expr = ExpressionWrapper(F('price') * F('quantity'), output_field=DecimalField(max_digits=12, decimal_places=2))
    items_qs = OrderItem.objects.filter(order__in=orders)

    by_category = list(
        items_qs.values('product__category__name')
        .annotate(total_qty=Sum('quantity'), total_sum=Sum(subtotal_expr))
        .order_by('-total_sum')
    )
    top_by_revenue = list(
        items_qs.values('product__name')
        .annotate(total_qty=Sum('quantity'), total_sum=Sum(subtotal_expr))
        .order_by('-total_sum')[:10]
    )
    daily = list(
        orders.annotate(day=TruncDay('created_at'))
        .values('day').annotate(total=Sum('total_price'), cnt=Count('id'))
        .order_by('day')
    )

    if request.GET.get('format') == 'csv':
        import csv
        from django.http import HttpResponse
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Товар', 'Продано (шт.)', 'Выручка (₽)'])
        for p in top_by_revenue:
            writer.writerow([p['product__name'], p['total_qty'], p['total_sum']])
        return response

    return JsonResponse({
        'total_count': total_count,
        'total_revenue': str(total_revenue),
        'avg_order': str(avg_order),
        'by_category': [{'name': c['product__category__name'] or 'Без категории', 'qty': c['total_qty'], 'sum': str(c['total_sum'] or 0)} for c in by_category],
        'top_by_revenue': [{'name': p['product__name'], 'qty': p['total_qty'], 'sum': str(p['total_sum'] or 0)} for p in top_by_revenue],
        'daily': [{'date': e['day'].strftime('%d.%m'), 'total': float(e['total']), 'cnt': e['cnt']} for e in daily],
    })


def reports_customers(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)

    orders = _parse_date_range(request).exclude(status='cancelled')
    unique_customers = orders.values('phone').distinct().count()
    total_revenue = orders.aggregate(t=Sum('total_price'))['t'] or Decimal('0')
    avg_per_customer = (total_revenue / unique_customers).quantize(Decimal('1')) if unique_customers else Decimal('0')

    top_customers = list(
        orders.values('name', 'phone')
        .annotate(order_count=Count('id'), total_spent=Sum('total_price'), last_order=Max('created_at'))
        .order_by('-total_spent')[:15]
    )
    all_time = Order.objects.exclude(status='cancelled').values('phone').annotate(cnt=Count('id'))
    one_time = sum(1 for c in all_time if c['cnt'] == 1)
    returning = sum(1 for c in all_time if c['cnt'] >= 2)

    if request.GET.get('format') == 'csv':
        import csv
        from django.http import HttpResponse
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="customers_report.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Клиент', 'Телефон', 'Заказов', 'Потрачено (₽)', 'Последний заказ'])
        for c in top_customers:
            writer.writerow([c['name'], c['phone'], c['order_count'], c['total_spent'], c['last_order'].strftime('%d.%m.%Y')])
        return response

    return JsonResponse({
        'unique_customers': unique_customers,
        'avg_per_customer': str(avg_per_customer),
        'one_time': one_time,
        'returning': returning,
        'top_customers': [{'name': c['name'], 'phone': c['phone'], 'order_count': c['order_count'], 'total_spent': str(c['total_spent']), 'last_order': c['last_order'].strftime('%d.%m.%Y')} for c in top_customers],
    })


def reports_stock(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)

    products = Product.objects.select_related('category').prefetch_related('inventory')
    total = products.count()
    available_cnt = products.filter(is_available=True).count()
    out_cnt = low_cnt = 0
    stock_data = []

    for p in products:
        try:
            qty = p.inventory.quantity
        except Exception:
            qty = None
        if qty is None:
            st = 'unknown'
        elif qty == 0:
            st = 'out'; out_cnt += 1
        elif qty < 5:
            st = 'low'; low_cnt += 1
        else:
            st = 'ok'
        stock_data.append({'name': p.name, 'category': str(p.category) if p.category else 'Без категории', 'available': p.is_available, 'qty': qty, 'status': st})

    stock_data.sort(key=lambda x: {'out': 0, 'low': 1, 'unknown': 2, 'ok': 3}.get(x['status'], 2))

    if request.GET.get('format') == 'csv':
        import csv
        from django.http import HttpResponse
        labels = {'ok': 'В наличии', 'low': 'Мало', 'out': 'Закончился', 'unknown': 'Не указан'}
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="stock_report.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Товар', 'Категория', 'Доступен', 'Кол-во', 'Статус'])
        for p in stock_data:
            writer.writerow([p['name'], p['category'], 'Да' if p['available'] else 'Нет', p['qty'] if p['qty'] is not None else '—', labels.get(p['status'], '—')])
        return response

    return JsonResponse({'total': total, 'available': available_cnt, 'out_of_stock': out_cnt, 'low_stock': low_cnt, 'products': stock_data})


def reports_export(request):
    import csv
    from django.http import HttpResponse
    if not request.user.is_staff:
        return redirect('index')
    orders = _parse_date_range(request)
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="report.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['№', 'Клиент', 'Телефон', 'Адрес', 'Сумма', 'Статус', 'Дата'])
    for order in orders.order_by('-created_at'):
        writer.writerow([
            order.pk, order.name, order.phone, order.address,
            order.total_price, order.get_status_display(),
            order.created_at.strftime('%d.%m.%Y %H:%M'),
        ])
    return response


def inventory_update(request, product_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    p = get_object_or_404(Product, pk=product_id)
    try:
        quantity = max(0, int(request.POST.get('quantity', 0)))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Неверное количество'}, status=400)
    Inventory.objects.update_or_create(product=p, defaults={'quantity': quantity})
    return JsonResponse({'ok': True, 'quantity': quantity})


def global_packaging_list(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    opts = list(GlobalPackagingOption.objects.values('id', 'name', 'price_modifier', 'order'))
    for o in opts:
        o['price_modifier'] = str(o['price_modifier'])
    return JsonResponse({'options': opts})


def global_packaging_save(request, pk=None):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    opt = get_object_or_404(GlobalPackagingOption, pk=pk) if pk else GlobalPackagingOption()
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Название обязательно'}, status=400)
    try:
        modifier = Decimal(request.POST.get('price_modifier', '0'))
    except InvalidOperation:
        return JsonResponse({'error': 'Неверная надбавка'}, status=400)
    try:
        order = int(request.POST.get('order', 0))
    except (ValueError, TypeError):
        order = 0
    opt.name = name
    opt.price_modifier = modifier
    opt.order = order
    opt.save()
    return JsonResponse({'ok': True, 'id': opt.pk, 'name': opt.name, 'price_modifier': str(opt.price_modifier), 'order': opt.order})


def global_packaging_delete(request, pk):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    opt = get_object_or_404(GlobalPackagingOption, pk=pk)
    opt.delete()
    return JsonResponse({'ok': True})


def orders_poll(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    since_id = request.GET.get('since', 0)
    try:
        since_id = int(since_id)
    except (ValueError, TypeError):
        since_id = 0
    new_orders = list(
        Order.objects.filter(pk__gt=since_id, status='new')
        .order_by('-pk')
        .values('pk', 'name', 'total_price', 'created_at')[:5]
    )
    max_id = Order.objects.aggregate(m=Max('pk'))['m'] or 0
    return JsonResponse({
        'new_orders': [
            {'id': o['pk'], 'name': o['name'], 'total': str(o['total_price'])}
            for o in new_orders
        ],
        'max_id': max_id,
    })


def banner_get(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    b = Banner.get_active()
    return JsonResponse({
        'tag': b.tag,
        'title': b.title,
        'subtitle': b.subtitle,
        'btn1_text': b.btn1_text,
        'btn1_url': b.btn1_url,
        'btn2_text': b.btn2_text,
        'btn2_url': b.btn2_url,
        'image_url': b.image.url if b.image else '',
    })


def banner_save(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'forbidden'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    b = Banner.get_active()
    b.tag = request.POST.get('tag', '').strip()
    b.title = request.POST.get('title', '').strip()
    b.subtitle = request.POST.get('subtitle', '').strip()
    b.btn1_text = request.POST.get('btn1_text', '').strip()
    b.btn1_url = request.POST.get('btn1_url', '').strip()
    b.btn2_text = request.POST.get('btn2_text', '').strip()
    b.btn2_url = request.POST.get('btn2_url', '').strip()
    if not b.title:
        return JsonResponse({'error': 'Заголовок обязателен'}, status=400)
    if request.POST.get('clear_image') == 'on':
        if b.image:
            b.image.delete(save=False)
        b.image = None
    elif 'image' in request.FILES:
        if b.image:
            b.image.delete(save=False)
        b.image = request.FILES['image']
    b.save()
    return JsonResponse({'ok': True, 'image_url': b.image.url if b.image else ''})


def page_not_found(request, exception=None):
    return render(request, '404.html', status=404)


def address_save(request, pk=None):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'auth'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'method'}, status=405)
    addr = get_object_or_404(Address, pk=pk, user=request.user) if pk else Address(user=request.user)
    street = request.POST.get('street', '').strip()
    house = request.POST.get('house', '').strip()
    if not street or not house:
        return JsonResponse({'error': 'Улица и дом обязательны'}, status=400)
    addr.title = request.POST.get('title', 'Домашний').strip() or 'Домашний'
    addr.street = street
    addr.house = house
    addr.flat = request.POST.get('flat', '').strip()
    addr.entrance = request.POST.get('entrance', '').strip()
    is_default = request.POST.get('is_default') == 'on'
    if is_default:
        Address.objects.filter(user=request.user).update(is_default=False)
    addr.is_default = is_default
    if not Address.objects.filter(user=request.user).exclude(pk=addr.pk or 0).exists():
        addr.is_default = True
    addr.save()
    return JsonResponse({'ok': True, 'id': addr.pk, 'title': addr.title,
                         'full_address': addr.full_address, 'is_default': addr.is_default})


def address_delete(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'auth'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'method'}, status=405)
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = addr.is_default
    addr.delete()
    if was_default:
        first = Address.objects.filter(user=request.user).first()
        if first:
            first.is_default = True
            first.save(update_fields=['is_default'])
    return JsonResponse({'ok': True})


def address_set_default(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'auth'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'method'}, status=405)
    Address.objects.filter(user=request.user).update(is_default=False)
    addr = get_object_or_404(Address, pk=pk, user=request.user)
    addr.is_default = True
    addr.save(update_fields=['is_default'])
    return JsonResponse({'ok': True})


def order_repeat(request, pk):
    if not request.user.is_authenticated:
        return redirect('auth')
    order = get_object_or_404(Order, pk=pk, user=request.user)
    c = Cart(request)
    for item in order.items.select_related('product'):
        try:
            c.add(item.product, quantity=item.quantity, override=False)
        except Exception:
            pass
    return redirect('cart')


def profile_update(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'auth'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'method'}, status=405)
    user = request.user
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    if not first_name:
        return JsonResponse({'error': 'Имя обязательно'}, status=400)
    if not email:
        return JsonResponse({'error': 'Email обязателен'}, status=400)
    if User.objects.filter(username=email).exclude(pk=user.pk).exists():
        return JsonResponse({'error': 'Этот email уже занят'}, status=400)
    phone = request.POST.get('phone', '').strip()
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.username = email
    user.save(update_fields=['first_name', 'last_name', 'email', 'username'])
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.phone = phone
    profile.save(update_fields=['phone'])
    return JsonResponse({'ok': True, 'first_name': first_name, 'last_name': last_name, 'email': email, 'phone': phone})


def password_change(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'auth'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'method'}, status=405)
    user = request.user
    current = request.POST.get('current_password', '')
    new1 = request.POST.get('new_password1', '')
    new2 = request.POST.get('new_password2', '')
    if not user.check_password(current):
        return JsonResponse({'error': 'Неверный текущий пароль'}, status=400)
    if len(new1) < 8:
        return JsonResponse({'error': 'Пароль должен быть не менее 8 символов'}, status=400)
    if new1 != new2:
        return JsonResponse({'error': 'Пароли не совпадают'}, status=400)
    user.set_password(new1)
    user.save()
    from django.contrib.auth import update_session_auth_hash
    update_session_auth_hash(request, user)
    return JsonResponse({'ok': True})


def about(request):
    return render(request, 'shop/about.html')


def quick_order(request):
    if request.method == 'POST':
        Order.objects.create(
            name=request.POST.get('name', ''),
            phone=request.POST.get('phone', ''),
            address=request.POST.get('occasion', ''),
            comment=request.POST.get('comment', ''),
        )
    return redirect('index')
