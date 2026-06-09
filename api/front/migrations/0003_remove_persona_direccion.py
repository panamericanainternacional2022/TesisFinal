# Generated manually - Remove direccion field from Persona (redundant with Edificio.direccion)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('front', '0002_add_alerts_fields_to_usuario'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='persona',
            name='direccion',
        ),
    ]
