from django.db import models


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
