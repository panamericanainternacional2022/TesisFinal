from apps.buildings.models import EquipoMonitoreo


def _crear_equipos_para_edificio(edificio, con_bomba, con_elevador):
    if con_bomba:
        EquipoMonitoreo.objects.get_or_create(
            id_edificio=edificio, tipo=EquipoMonitoreo.TIPO_BOMBA,
            defaults={"nb_equipo": f"Bomba de agua - {edificio.nb_edificio}"},
        )
    if con_elevador:
        EquipoMonitoreo.objects.get_or_create(
            id_edificio=edificio, tipo=EquipoMonitoreo.TIPO_ELEVADOR,
            defaults={"nb_equipo": f"Elevador - {edificio.nb_edificio}"},
        )


def _sincronizar_equipos_para_edificio(edificio, con_bomba, con_elevador):
    if con_bomba:
        EquipoMonitoreo.objects.get_or_create(
            id_edificio=edificio, tipo=EquipoMonitoreo.TIPO_BOMBA,
            defaults={"nb_equipo": f"Bomba de agua - {edificio.nb_edificio}"},
        )
    else:
        EquipoMonitoreo.objects.filter(
            id_edificio=edificio, tipo=EquipoMonitoreo.TIPO_BOMBA,
        ).delete()
    if con_elevador:
        EquipoMonitoreo.objects.get_or_create(
            id_edificio=edificio, tipo=EquipoMonitoreo.TIPO_ELEVADOR,
            defaults={"nb_equipo": f"Elevador - {edificio.nb_edificio}"},
        )
    else:
        EquipoMonitoreo.objects.filter(
            id_edificio=edificio, tipo=EquipoMonitoreo.TIPO_ELEVADOR,
        ).delete()
