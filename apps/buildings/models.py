from django.db import models


class Edificio(models.Model):
    id_edificio = models.AutoField(primary_key=True)
    nb_edificio = models.CharField(max_length=255)
    rif = models.CharField(max_length=20, unique=True)
    direccion = models.TextField()

    class Meta:
        db_table = "edificio"

    def __str__(self):
        return self.nb_edificio


class EquipoMonitoreo(models.Model):
    TIPO_BOMBA = "bomba"
    TIPO_ELEVADOR = "elevador"
    TIPO_CHOICES = [
        (TIPO_BOMBA, "Bomba de agua"),
        (TIPO_ELEVADOR, "Elevador"),
    ]

    STATUS_OPERATIVO = "operativo"
    STATUS_FALLA = "falla"
    STATUS_MANTENIMIENTO = "mantenimiento"
    STATUS_CHOICES = [
        (STATUS_OPERATIVO, "Operativo"),
        (STATUS_FALLA, "Falla"),
        (STATUS_MANTENIMIENTO, "Mantenimiento"),
    ]

    id_equipo_monitoreo = models.AutoField(primary_key=True)
    nb_equipo = models.CharField(max_length=255)
    id_edificio = models.ForeignKey(
        Edificio, on_delete=models.CASCADE, db_column="id_edificio"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_BOMBA)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPERATIVO)

    class Meta:
        db_table = "equipo_monitoreo"

    def __str__(self):
        return self.nb_equipo


class UsuarioEdificio(models.Model):
    id_usuario_beneficiario = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        "users.Usuario", on_delete=models.CASCADE, db_column="id_usuario"
    )
    id_edificio = models.ForeignKey(
        Edificio, on_delete=models.CASCADE, db_column="id_edificio"
    )

    class Meta:
        db_table = "usuario_edificio"

    def __str__(self):
        edificio = self.id_edificio.nb_edificio if self.id_edificio else "?"
        usuario = self.id_usuario.username if self.id_usuario else "?"
        return f"{usuario} -> {edificio}"
