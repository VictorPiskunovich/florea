from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0008_global_packaging_option'),
    ]

    operations = [
        migrations.CreateModel(
            name='Banner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tag', models.CharField(default='🌷 Доставка по Омску за 2 часа', max_length=200, verbose_name='Тег над заголовком')),
                ('title', models.CharField(default='Свежие цветы с душой для вас', max_length=300, verbose_name='Заголовок')),
                ('subtitle', models.TextField(default='Букеты ручной работы, комнатные растения и цветочные композиции. Доставим в любой район Омска.', verbose_name='Подзаголовок')),
                ('btn1_text', models.CharField(default='Смотреть каталог', max_length=100, verbose_name='Кнопка 1 — текст')),
                ('btn1_url', models.CharField(default='/catalog/', max_length=200, verbose_name='Кнопка 1 — ссылка')),
                ('btn2_text', models.CharField(blank=True, default='Заказать звонок', max_length=100, verbose_name='Кнопка 2 — текст')),
                ('btn2_url', models.CharField(blank=True, default='#contacts', max_length=200, verbose_name='Кнопка 2 — ссылка')),
            ],
            options={
                'verbose_name': 'Баннер главной страницы',
            },
        ),
    ]
