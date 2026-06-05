from django.db import models


class AccionPrev(models.Model):
    id_accion_prev = models.AutoField(primary_key=True)
    id_equipo_monitoreo = models.ForeignKey(
        "EquipoMonitoreo",
        models.DO_NOTHING,
        db_column="id_equipo_monitoreo",
        blank=True,
        null=True,
    )
    id_dispos_sensor = models.ForeignKey(
        "DisposSensor",
        models.DO_NOTHING,
        db_column="id_dispos_sensor",
        blank=True,
        null=True,
    )
    parametro = models.TextField(blank=True, null=True)
    valor_min = models.FloatField(blank=True, null=True)
    valor_max = models.FloatField(blank=True, null=True)
    accion_preventiva = models.TextField(blank=True, null=True)
    id_status = models.ForeignKey(
        "Status", models.DO_NOTHING, db_column="id_status", blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "accion_prev"


class DisposSensor(models.Model):
    id_dispos_sensor = models.AutoField(primary_key=True)
    nb_sensor = models.TextField(blank=True, null=True)
    modelo_iot = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "dispos_sensor"


class Edificio(models.Model):
    id_edificio = models.AutoField(primary_key=True)
    nb_edificio = models.TextField(blank=True, null=True)
    rif = models.CharField(max_length=20, blank=True, null=True, unique=True)
    direccion = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "edificio"


class EquipoMonitoreo(models.Model):
    id_equipo_monitoreo = models.AutoField(primary_key=True)
    nb_equipo = models.TextField(blank=True, null=True)
    id_edificio = models.ForeignKey(
        Edificio, models.DO_NOTHING, db_column="id_edificio", blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "equipo_monitoreo"


class EquipoSensor(models.Model):
    id_equipo_sensor = models.AutoField(primary_key=True)
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo,
        models.DO_NOTHING,
        db_column="id_equipo_monitoreo",
        blank=True,
        null=True,
    )
    id_dispos_sensor = models.ForeignKey(
        DisposSensor,
        models.DO_NOTHING,
        db_column="id_dispos_sensor",
        blank=True,
        null=True,
    )
    tipo_valor_capt = models.FloatField(blank=True, null=True)
    fecha_hora_lect = models.DateTimeField(blank=True, null=True)
    descripcion_falla = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "equipo_sensor"


class HistoricoFalla(models.Model):
    id_historico_falla = models.AutoField(primary_key=True)
    id_equipo_sensor = models.ForeignKey(
        EquipoSensor,
        models.DO_NOTHING,
        db_column="id_equipo_sensor",
        blank=True,
        null=True,
    )
    fecha = models.DateTimeField(blank=True, null=True)
    id_status_equipo_monitoreo = models.ForeignKey(
        "StatusEquipoMonitoreo",
        models.DO_NOTHING,
        db_column="id_status_equipo_monitoreo",
        blank=True,
        null=True,
    )

    class Meta:
        managed = False
        db_table = "historico_falla"


class Notificacion(models.Model):
    id_notificacion = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        "Usuario", models.DO_NOTHING, db_column="id_usuario", blank=True, null=True
    )
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo,
        models.DO_NOTHING,
        db_column="id_equipo_monitoreo",
        blank=True,
        null=True,
    )
    fecha = models.DateTimeField(blank=True, null=True)
    mensaje = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "notificacion"


class Persona(models.Model):
    id_persona = models.AutoField(primary_key=True)
    ci = models.IntegerField(blank=True, null=True)
    name = models.TextField(blank=True, null=True)
    apellido = models.TextField(blank=True, null=True)
    email = models.TextField(blank=True, null=True)
    telefono = models.TextField(blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "persona"


class Status(models.Model):
    id_status = models.AutoField(primary_key=True)
    nb_status = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "status"


class StatusEquipoMonitoreo(models.Model):
    id_status_equipo_monitoreo = models.AutoField(primary_key=True)
    id_status = models.ForeignKey(
        Status, models.DO_NOTHING, db_column="id_status", blank=True, null=True
    )
    id_equipo_monitoreo = models.ForeignKey(
        EquipoMonitoreo,
        models.DO_NOTHING,
        db_column="id_equipo_monitoreo",
        blank=True,
        null=True,
    )

    class Meta:
        managed = False
        db_table = "status_equipo_monitoreo"


class Usuario(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    username = models.TextField(blank=True, null=True)
    password = models.TextField(blank=True, null=True)
    id_persona = models.ForeignKey(
        Persona, models.DO_NOTHING, db_column="id_persona", blank=True, null=True
    )
    rol = models.TextField(blank=True, null=True, default="US")
    registrado = models.BooleanField(default=False)
    alerts_disabled = models.BooleanField(default=False)
    alerts_disabled_until = models.FloatField(null=True, blank=True)  # Unix timestamp, None = indefinite

    class Meta:
        managed = False
        db_table = "usuario"


class UsuarioEdificio(models.Model):
    id_usuario_beneficiario = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey(
        Usuario, models.DO_NOTHING, db_column="id_usuario", blank=True, null=True
    )
    id_edificio = models.ForeignKey(
        Edificio, models.DO_NOTHING, db_column="id_edificio", blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = "usuario_edificio"
