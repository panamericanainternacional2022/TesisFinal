from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('front', '0002_persona_direccion_usuario_rol'),
    ]

    operations = [
        migrations.AlterField(
            model_name='edificio',
            name='rif',
            field=models.CharField(max_length=20, unique=True),
        ),
    ]
