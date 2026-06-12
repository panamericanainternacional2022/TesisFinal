from django.db import models


class Notificacion(models.Model):
    id_notificacion = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        "users.Usuario", on_delete=models.CASCADE, db_column="id_usuario", blank=True, null=True
    )
    id_equipo_monitoreo = models.ForeignKey(
        "buildings.MonitoringEquipment", on_delete=models.CASCADE, db_column="id_equipo_monitoreo",
        blank=True, null=True,
    )
    fecha = models.DateTimeField()
    mensaje = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "notificacion"

    def __str__(self):
        return f"[{self.fecha}] {self.mensaje[:60]}"


class UmbralConfig(models.Model):
    variable = models.CharField(max_length=50, unique=True)
    direction = models.CharField(max_length=10, default="higher")
    low = models.FloatField()
    medium = models.FloatField(null=True, blank=True)
    high = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "umbral_config"
        verbose_name = "Configuración de Umbral"
        verbose_name_plural = "Configuraciones de Umbrales"

    def __str__(self):
        return f"{self.variable}: {self.direction} low={self.low} med={self.medium} high={self.high}"
