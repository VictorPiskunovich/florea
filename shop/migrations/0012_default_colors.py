from django.db import migrations

COLORS = [
    ('Красный',     'red',       '#ef4444', 0),
    ('Розовый',     'pink',      '#f472b6', 1),
    ('Белый',       'white',     '#f3f4f6', 2),
    ('Жёлтый',      'yellow',    '#facc15', 3),
    ('Фиолетовый',  'purple',    '#a855f7', 4),
    ('Оранжевый',   'orange',    '#fb923c', 5),
    ('Синий',       'blue',      '#60a5fa', 6),
    ('Зелёный',     'green',     '#4ade80', 7),
    ('Персиковый',  'peach',     '#fca5a5', 8),
    ('Бордовый',    'burgundy',  '#9f1239', 9),
]


def add_colors(apps, schema_editor):
    Color = apps.get_model('shop', 'Color')
    for name, slug, hex_code, order in COLORS:
        Color.objects.get_or_create(slug=slug, defaults={'name': name, 'hex_code': hex_code, 'order': order})


def remove_colors(apps, schema_editor):
    Color = apps.get_model('shop', 'Color')
    Color.objects.filter(slug__in=[c[1] for c in COLORS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0011_color_product_colors'),
    ]

    operations = [
        migrations.RunPython(add_colors, remove_colors),
    ]
