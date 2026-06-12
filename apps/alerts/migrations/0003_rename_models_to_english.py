from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0002_alter_notificacion_mensaje"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Notificacion",
            new_name="Notification",
        ),
        migrations.RenameModel(
            old_name="UmbralConfig",
            new_name="ThresholdConfig",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="id_notificacion",
            new_name="id",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="id_usuario",
            new_name="user",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="id_equipo_monitoreo",
            new_name="monitoring_equipment",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="fecha",
            new_name="date",
        ),
        migrations.RenameField(
            model_name="notification",
            old_name="mensaje",
            new_name="message",
        ),
        migrations.AlterField(
            model_name="notification",
            name="id",
            field=models.AutoField(db_column="id_notificacion", primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="notification",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_column="id_usuario",
                null=True,
                on_delete=models.deletion.CASCADE,
                to="users.usuario",
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="monitoring_equipment",
            field=models.ForeignKey(
                blank=True,
                db_column="id_equipo_monitoreo",
                null=True,
                on_delete=models.deletion.CASCADE,
                to="buildings.monitoringequipment",
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="date",
            field=models.DateTimeField(db_column="fecha"),
        ),
        migrations.AlterField(
            model_name="notification",
            name="message",
            field=models.JSONField(blank=True, db_column="mensaje", default=dict),
        ),
    ]
