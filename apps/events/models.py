from django.db import models


class Notification(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_notificacion")
    user = models.ForeignKey(
        "users.Usuario", on_delete=models.CASCADE, db_column="id_usuario", blank=True, null=True
    )
    monitoring_equipment = models.ForeignKey(
        "buildings.MonitoringEquipment", on_delete=models.CASCADE, db_column="id_equipo_monitoreo",
        blank=True, null=True,
    )
    date = models.DateTimeField(db_column="fecha", db_index=True)
    message = models.JSONField(default=dict, blank=True, db_column="mensaje")

    class Meta:
        db_table = "notificacion"

    def __str__(self) -> str:
        msg_str = str(self.message)
        return f"[{self.date}] {msg_str[:60]}"
