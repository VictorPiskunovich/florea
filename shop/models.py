from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    name = models.CharField('Название', max_length=255)
    slug = models.SlugField(unique=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='products', verbose_name='Категория')
    name = models.CharField('Название', max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField('Описание', blank=True)
    price = models.DecimalField('Цена', max_digits=10, decimal_places=2)
    image = models.ImageField('Фото', upload_to='products/', blank=True)
    is_available = models.BooleanField('В наличии', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self):
        return self.name

    @property
    def stock(self):
        inv = getattr(self, '_inventory', None)
        if inv is None:
            try:
                return self.inventory.quantity
            except Inventory.DoesNotExist:
                return 0
        return inv

    @property
    def stock_status(self):
        qty = self.stock
        if qty == 0:
            return 'out'
        if qty < 5:
            return 'low'
        return 'ok'


class Inventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE,
                                    related_name='inventory', verbose_name='Товар')
    quantity = models.PositiveIntegerField('Количество на складе', default=0)

    class Meta:
        verbose_name = 'Остаток на складе'
        verbose_name_plural = 'Остатки на складе'

    def __str__(self):
        return f'{self.product.name} — {self.quantity} шт.'


class Order(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('processing', 'В обработке'),
        ('delivering', 'Доставляется'),
        ('done', 'Выполнен'),
        ('cancelled', 'Отменён'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='orders', verbose_name='Пользователь')
    name = models.CharField('Имя', max_length=255)
    phone = models.CharField('Телефон', max_length=20)
    address = models.TextField('Адрес доставки')
    comment = models.TextField('Комментарий', blank=True)
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='new')
    total_price = models.DecimalField('Сумма заказа', max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self):
        return f'Заказ #{self.pk} — {self.name}'

    def calculate_total(self):
        total = sum(item.subtotal() for item in self.items.all())
        self.total_price = total
        self.save(update_fields=['total_price'])
        return total


class GlobalPackagingOption(models.Model):
    name = models.CharField('Название', max_length=100)
    price_modifier = models.DecimalField('Надбавка к цене', max_digits=8, decimal_places=2, default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Глобальный вид упаковки'

    def __str__(self):
        return self.name


class PackagingOption(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='packaging_options')
    name = models.CharField('Название', max_length=100)
    price_modifier = models.DecimalField('Надбавка к цене', max_digits=8, decimal_places=2, default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.product.name} — {self.name}'


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField('Фото', upload_to='products/gallery/')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']


class Banner(models.Model):
    tag = models.CharField('Тег над заголовком', max_length=200, default='🌷 Доставка по Омску за 2 часа')
    title = models.CharField('Заголовок', max_length=300, default='Свежие цветы с душой для вас')
    subtitle = models.TextField('Подзаголовок', default='Букеты ручной работы, комнатные растения и цветочные композиции. Доставим в любой район Омска.')
    btn1_text = models.CharField('Кнопка 1 — текст', max_length=100, default='Смотреть каталог')
    btn1_url = models.CharField('Кнопка 1 — ссылка', max_length=200, default='/catalog/')
    btn2_text = models.CharField('Кнопка 2 — текст', max_length=100, default='Заказать звонок', blank=True)
    btn2_url = models.CharField('Кнопка 2 — ссылка', max_length=200, default='#contacts', blank=True)
    image = models.ImageField('Фоновое изображение', upload_to='banner/', blank=True)

    class Meta:
        verbose_name = 'Баннер главной страницы'

    def __str__(self):
        return 'Баннер главной страницы'

    @classmethod
    def get_active(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        verbose_name = 'Избранное'
        verbose_name_plural = 'Избранное'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE,
                               related_name='items', verbose_name='Заказ')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='Товар')
    quantity = models.PositiveIntegerField('Количество', default=1)
    price = models.DecimalField('Цена на момент заказа', max_digits=10, decimal_places=2)
    extras = models.CharField('Доп. параметры', max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'

    def subtotal(self):
        return self.price * self.quantity

    def save(self, *args, **kwargs):
        if not self.pk and not self.price:
            self.price = self.product.price
        super().save(*args, **kwargs)
