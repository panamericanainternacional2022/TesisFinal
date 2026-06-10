from django.db import models

# --- TABLAS MAESTRAS / INDEPENDIENTES ---




class Persona(models.Model):
    id_persona = models.AutoField(primary_key=True)
    ci = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)
    email = models.EmailField(max_length=255)
    telefono = models.CharField(max_length=50)

    class Meta:
        db_table = "persona"

    def __str__(self):
        return f"{self.name} {self.apellido}"


class Edificio(models.Model):
    id_edificio = models.AutoField(primary_key=True)
    nb_edificio = models.CharField(max_length=255)
    rif = models.CharField(max_length=20, unique=True)
    direccion = models.TextField()

    class Meta:
        db_table = "edificio"

    def __str__(self):
        return self.nb_edificio





# --- TABLAS CON RELACIONES ---


class Usuario(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)
    id_persona = models.ForeignKey(
        Persona, on_delete=models.CASCADE, db_column="id_persona"
    )
    rol = models.CharField(max_length=2, default="US")
    registrado = models.BooleanField(default=False)
    alerts_disabled = models.BooleanField(default=False)
    alerts_disabled_until = models.FloatField(null=True, blank=True)  # Unix timestamp, None = indefinite

    class Meta:
        db_table = "usuario"

    def __str__(self):
        return self.username


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
        Usuario, on_delete=models.CASCADE, db_column="id_usuario"
    )
    id_edificio = models.ForeignKey(
        Edificio, on_delete=models.CASCADE, db_column="id_edificio"
    )

    class Meta:
        db_table = "usuario_edificio"


class Notificacion(models.Model):
    id_notificacion = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, db_column="id_usuario", blank=True, null=True
    )
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo, on_delete=models.CASCADE, db_column="id_equipo_monitoreo",
        blank=True, null=True,
    )
    fecha = models.DateTimeField()
    mensaje = models.TextField()

    class Meta:
        db_table = "notificacion"
