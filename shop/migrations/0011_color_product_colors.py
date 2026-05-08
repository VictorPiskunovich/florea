from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0010_banner_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='Color',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, verbose_name='Название')),
                ('slug', models.SlugField(unique=True)),
                ('hex_code', models.CharField(default='#cccccc', max_length=7, verbose_name='HEX-цвет')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')),
            ],
            options={
                'verbose_name': 'Цвет',
                'verbose_name_plural': 'Цвета',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='product',
            name='colors',
            field=models.ManyToManyField(blank=True, related_name='products', to='shop.color', verbose_name='Цвета'),
        ),
    ]
