from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0012_default_colors'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Address',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Домашний', max_length=100, verbose_name='Название')),
                ('street', models.CharField(max_length=255, verbose_name='Улица')),
                ('house', models.CharField(max_length=20, verbose_name='Дом')),
                ('flat', models.CharField(blank=True, max_length=20, verbose_name='Квартира')),
                ('entrance', models.CharField(blank=True, max_length=50, verbose_name='Подъезд/этаж')),
                ('is_default', models.BooleanField(default=False, verbose_name='Основной')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addresses', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Адрес доставки',
                'verbose_name_plural': 'Адреса доставки',
                'ordering': ['-is_default', 'id'],
            },
        ),
    ]
