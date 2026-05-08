from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0009_banner'),
    ]

    operations = [
        migrations.AddField(
            model_name='banner',
            name='image',
            field=models.ImageField(blank=True, upload_to='banner/', verbose_name='Фоновое изображение'),
        ),
    ]
