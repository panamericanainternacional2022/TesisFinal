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
    date = models.DateTimeField(db_column="fecha")
    message = models.JSONField(default=dict, blank=True, db_column="mensaje")

    class Meta:
        db_table = "notificacion"

    def __str__(self) -> str:
        msg_str = str(self.message)
        return f"[{self.date}] {msg_str[:60]}"


class ThresholdConfig(models.Model):
    id = models.AutoField(primary_key=True)
    building = models.ForeignKey(
        "buildings.Building",
        on_delete=models.CASCADE,
        db_column="id_edificio",
        related_name="thresholds",
    )
    variable = models.CharField(max_length=50)
    direction = models.CharField(max_length=10, default="higher")
    low = models.FloatField()
    medium = models.FloatField(null=True, blank=True)
    high = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "umbral_config"
        unique_together = ("building", "variable")
        verbose_name = "Configuración de Umbral"
        verbose_name_plural = "Configuraciones de Umbrales"

    def __str__(self) -> str:
        return f"[Ed.{self.building_id}] {self.variable}: {self.direction} low={self.low} med={self.medium} high={self.high}"


class SensorLimitConfig(models.Model):
    id = models.AutoField(primary_key=True)
    building = models.ForeignKey(
        "buildings.Building",
        on_delete=models.CASCADE,
        db_column="id_edificio",
        related_name="sensor_limits",
    )
    variable = models.CharField(max_length=50)
    max_value = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "limite_sensor_config"
        unique_together = ("building", "variable")
        verbose_name = "Límite de Sensor"
        verbose_name_plural = "Límites de Sensores"

    def __str__(self) -> str:
        return f"[Ed.{self.building_id}] {self.variable}: max={self.max_value}"

