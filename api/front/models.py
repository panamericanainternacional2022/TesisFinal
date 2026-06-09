from django.db import models

# --- TABLAS MAESTRAS / INDEPENDIENTES ---


class Persona(models.Model):
    id_persona = models.AutoField(primary_key=True)
    ci = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    apellido = models.CharField(max_length=255)
    email = models.EmailField(max_length=255)
    telefono = models.CharField(max_length=50)
    direccion = models.TextField(blank=True, null=True)

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


class Status(models.Model):
    id_status = models.AutoField(primary_key=True)
    nb_status = models.CharField(max_length=255)

    class Meta:
        db_table = "status"
        verbose_name_plural = "Statuses"

    def __str__(self):
        return self.nb_status


class DisposSensor(models.Model):
    id_dispos_sensor = models.AutoField(primary_key=True)
    nb_sensor = models.CharField(max_length=255)
    modelo_iot = models.CharField(max_length=255)

    class Meta:
        db_table = "dispos_sensor"

    def __str__(self):
        return f"{self.nb_sensor} ({self.modelo_iot})"


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
    id_equipo_monitoreo = models.AutoField(primary_key=True)
    nb_equipo = models.CharField(max_length=255)
    id_edificio = models.ForeignKey(
        Edificio, on_delete=models.CASCADE, db_column="id_edificio"
    )

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


class EquipoSensor(models.Model):
    id_equipo_sensor = models.AutoField(primary_key=True)
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo, on_delete=models.CASCADE, db_column="id_equipo_monitoreo"
    )
    id_dispos_sensor = models.ForeignKey(
        DisposSensor, on_delete=models.CASCADE, db_column="id_dispos_sensor"
    )
    tipo_valor_capt = models.FloatField()
    fecha_hora_lect = models.DateTimeField()
    descripcion_falla = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "equipo_sensor"


class StatusEquipoMonitoreo(models.Model):
    id_status_equipo_monitoreo = models.AutoField(primary_key=True)
    id_status = models.ForeignKey(
        Status, on_delete=models.CASCADE, db_column="id_status"
    )
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo, on_delete=models.CASCADE, db_column="id_equipo_monitoreo"
    )

    class Meta:
        db_table = "status_equipo_monitoreo"


class AccionPrev(models.Model):
    id_accion_prev = models.AutoField(primary_key=True)
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo, on_delete=models.CASCADE, db_column="id_equipo_monitoreo"
    )
    id_dispos_sensor = models.ForeignKey(
        DisposSensor, on_delete=models.CASCADE, db_column="id_dispos_sensor"
    )
    parametro = models.CharField(max_length=255)
    valor_min = models.FloatField()
    valor_max = models.FloatField()
    accion_preventiva = models.TextField()
    id_status = models.ForeignKey(
        Status, on_delete=models.CASCADE, db_column="id_status"
    )

    class Meta:
        db_table = "accion_prev"


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


class HistoricoFalla(models.Model):
    id_historico_falla = models.AutoField(primary_key=True)
    id_equipo_sensor = models.ForeignKey(
        EquipoSensor, on_delete=models.CASCADE, db_column="id_equipo_sensor"
    )
    fecha = models.DateTimeField()
    id_status_equipo_monitoreo = models.ForeignKey(
        StatusEquipoMonitoreo,
        on_delete=models.CASCADE,
        db_column="id_status_equipo_monitoreo",
    )

    class Meta:
        db_table = "historico_falla"


# Create your models here.
