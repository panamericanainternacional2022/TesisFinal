from django.db import models


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
    alerts_disabled_until = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "usuario"

    def __str__(self):
        return self.username
