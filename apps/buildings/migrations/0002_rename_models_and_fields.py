from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('buildings', '0001_initial'),
        ('users', '0002_alter_persona_apellido_and_more'),
    ]

    operations = [
        migrations.RenameModel(old_name='Edificio', new_name='Building'),
        migrations.RenameModel(old_name='EquipoMonitoreo', new_name='MonitoringEquipment'),
        migrations.RenameModel(old_name='UsuarioEdificio', new_name='UserBuilding'),
        migrations.RenameField(
            model_name='building', old_name='id_edificio', new_name='id',
        ),
        migrations.RenameField(
            model_name='building', old_name='nb_edificio', new_name='name',
        ),
        migrations.RenameField(
            model_name='building', old_name='direccion', new_name='address',
        ),
        migrations.RenameField(
            model_name='monitoringequipment', old_name='id_equipo_monitoreo', new_name='id',
        ),
        migrations.RenameField(
            model_name='monitoringequipment', old_name='nb_equipo', new_name='name',
        ),
        migrations.RenameField(
            model_name='monitoringequipment', old_name='tipo', new_name='equipment_type',
        ),
        migrations.RenameField(
            model_name='monitoringequipment', old_name='id_edificio', new_name='building',
        ),
        migrations.RenameField(
            model_name='userbuilding', old_name='id_usuario_beneficiario', new_name='id',
        ),
        migrations.RenameField(
            model_name='userbuilding', old_name='id_edificio', new_name='building',
        ),
        migrations.RenameField(
            model_name='userbuilding', old_name='id_usuario', new_name='user',
        ),
        migrations.AlterModelTable(
            name='building', table='edificio',
        ),
        migrations.AlterModelTable(
            name='monitoringequipment', table='equipo_monitoreo',
        ),
        migrations.AlterModelTable(
            name='userbuilding', table='usuario_edificio',
        ),
    ]
