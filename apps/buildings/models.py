from django.db import models


class Building(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_edificio")
    name = models.CharField(max_length=40, db_column="nb_edificio")
    rif = models.CharField(max_length=16, unique=True)
    address = models.CharField(max_length=100, db_column="direccion")
    floors = models.PositiveIntegerField(db_column="cantidad_pisos")

    class Meta:
        db_table = "edificio"

    def __str__(self) -> str:
        return self.name


class MonitoringEquipment(models.Model):
    TYPE_PUMP = "bomba"
    TYPE_ELEVATOR = "elevador"
    TYPE_CHOICES = [
        (TYPE_PUMP, "Bomba de agua"),
        (TYPE_ELEVATOR, "Elevador"),
    ]

    STATUS_OPERATIONAL = "operativo"
    STATUS_FAILURE = "falla"
    STATUS_MAINTENANCE = "mantenimiento"
    STATUS_CHOICES = [
        (STATUS_OPERATIONAL, "Operativo"),
        (STATUS_FAILURE, "Falla"),
        (STATUS_MAINTENANCE, "Mantenimiento"),
    ]

    id = models.AutoField(primary_key=True, db_column="id_equipo_monitoreo")
    name = models.CharField(max_length=255, db_column="nb_equipo")
    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, db_column="id_edificio",
        related_name="equipment",
    )
    equipment_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default=TYPE_PUMP,
        db_column="tipo",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OPERATIONAL,
    )

    class Meta:
        db_table = "equipo_monitoreo"

    def __str__(self) -> str:
        return self.name


class UserBuilding(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_asignacion")
    user = models.ForeignKey(
        "users.Usuario", on_delete=models.CASCADE, db_column="id_usuario",
        related_name="building_assignments",
    )
    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, db_column="id_edificio",
        related_name="user_assignments",
    )

    class Meta:
        db_table = "usuario_edificio"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "building"],
                name="uq_usuario_edificio",
            ),
        ]

    def __str__(self) -> str:
        b_name = self.building.name if self.building else "?"
        u_name = self.user.username if self.user else "?"
        return f"{u_name} -> {b_name}"
