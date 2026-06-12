import datetime as dt

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator

from apps.core.auth_decorators import _login_required, _admin_required, _is_admin_role
from apps.users.models import Usuario
from apps.buildings.models import Edificio, UsuarioEdificio, EquipoMonitoreo
from apps.alerts.models import Notificacion
from apps.alerts.views import _parse_notif_for_historial
from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, NO_RISK_VARS, PUMP_VARS, ELEVATOR_VARS,
    RISK_NAMES_ES, DEVICE_NAMES_ES,
)
from django.db.models import Q
from django.utils import timezone as tz


# ─── DASHBOARD / MENU ────────────────────────────────────────────


@_login_required
def menu_seleccion_view(request):
    rol = request.session.get("usuario_rol", "US")
    return render(request, "monitoring/menu_seleccion.html", {"rol": rol})


# ─── MONITOREO ──────────────────────────────────────────────────


@_login_required
def monitoreo_view(request):
    rol = request.session.get("usuario_rol", "US")
    if _is_admin_role(rol):
        edificios = list(Edificio.objects.all())
        edificio_id = request.GET.get("edificio")
        if edificio_id:
            try:
                edificio_id = int(edificio_id)
            except (ValueError, TypeError):
                edificio_id = edificios[0].id_edificio if edificios else 0
        else:
            edificio_id = edificios[0].id_edificio if edificios else 0
        import json as _json_mod
        config_json = _json_mod.dumps({
            "no_risk_vars": NO_RISK_VARS,
            "bomba_vars": PUMP_VARS,
            "elevador_vars": ELEVATOR_VARS,
            "var_names": VAR_NAMES,
            "units": UNITS,
            "edificio_id": edificio_id,
        })
        return render(
            request,
            "monitoring/monitoreo_dashboard.html",
            {
                "rol": rol,
                "edificios": edificios,
                "edificio_id": edificio_id,
                "config_json": config_json,
            },
        )

    usuario_id = request.session["usuario_id"]
    query = request.GET.get("q", "").strip()
    usuario_edificios = UsuarioEdificio.objects.filter(
        id_usuario_id=usuario_id
    ).values_list("id_edificio_id", flat=True)
    equipos = EquipoMonitoreo.objects.filter(
        id_edificio_id__in=list(usuario_edificios)
    ).select_related("id_edificio")

    if query:
        equipos = equipos.filter(
            Q(id_edificio__nb_edificio__icontains=query)
            | Q(id_edificio__rif__icontains=query)
        )

    data = []
    for eq in equipos:
        vars_list = PUMP_VARS if eq.tipo == EquipoMonitoreo.TIPO_BOMBA else ELEVATOR_VARS
        sensores = [
            {"nombre": VAR_NAMES.get(v, v), "unidad": UNITS.get(v, "")}
            for v in vars_list
        ]

        data.append(
            {
                "equipo": eq,
                "edificio": eq.id_edificio,
                "status": eq.get_status_display(),
                "sensores": sensores,
            }
        )

    return render(
        request,
        "monitoring/monitoreo.html",
        {
            "equipos_data": data,
            "rol": rol,
            "query": query,
            "edificio_id": data[0]["edificio"].id_edificio if len(data) > 0 else 0,
        },
    )


@_login_required
@_admin_required
def monitoreo_edificio_view(request, edificio_id):
    rol = request.session.get("usuario_rol", "US")
    edificio = get_object_or_404(Edificio, id_edificio=edificio_id)
    return render(
        request,
        "monitoring/monitoreo.html",
        {
            "rol": rol,
            "selected_edificio": edificio,
            "equipos_data": [],
            "query": "",
            "edificio_id": edificio_id,
        },
    )


# ─── HISTORIAL ──────────────────────────────────────────────────


@_login_required
def historial_view(request):
    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")

    edificio_id = request.GET.get("edificio", "").strip()
    if edificio_id.lower() in ("", "none", "null"):
        edificio_id = ""
    severidad = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    periodo_seleccionado = request.GET.get("periodo", "24h").strip()
    fecha_desde_raw = request.GET.get("fecha_desde", "").strip()
    fecha_hasta_raw = request.GET.get("fecha_hasta", "").strip()

    if _is_admin_role(rol):
        edificios = Edificio.objects.all()
        notificaciones = Notificacion.objects.all()
        if edificio_id:
            notificaciones = notificaciones.filter(
                id_equipo_monitoreo__id_edificio_id=edificio_id
            )
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        edificios = Edificio.objects.filter(id_edificio__in=usuario_edificios)

        if edificio_id:
            if edificio_id.isdigit() and int(edificio_id) in list(usuario_edificios):
                notificaciones = Notificacion.objects.filter(
                    id_equipo_monitoreo__id_edificio_id=edificio_id
                )
            else:
                notificaciones = Notificacion.objects.none()
        else:
            equipos = EquipoMonitoreo.objects.filter(
                id_edificio_id__in=list(usuario_edificios)
            ).values_list("id_equipo_monitoreo", flat=True)
            notificaciones = Notificacion.objects.filter(
                id_usuario_id=usuario_id
            ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))

    ALL_SEVERITIES = ["Info", "Bajo", "Medio", "Alto", "Crítico"]
    if severidad and severidad in ALL_SEVERITIES:
        notificaciones = notificaciones.filter(mensaje__icontains=f'"risk": "{severidad}"') | \
                         notificaciones.filter(mensaje__icontains=f'"risk":"{severidad}"')

    now = tz.now()
    DELTA_MAP = {
        "1h":  dt.timedelta(hours=1),
        "12h": dt.timedelta(hours=12),
        "24h": dt.timedelta(hours=24),
        "3d":  dt.timedelta(days=3),
        "7d":  dt.timedelta(days=7),
    }

    if periodo_seleccionado in DELTA_MAP:
        dt_desde = now - DELTA_MAP[periodo_seleccionado]
        notificaciones = notificaciones.filter(fecha__gte=dt_desde)
    elif periodo_seleccionado == "custom":
        if fecha_desde_raw:
            try:
                naive = dt.datetime.strptime(fecha_desde_raw, "%Y-%m-%d")
                notificaciones = notificaciones.filter(fecha__gte=tz.make_aware(naive))
            except ValueError:
                pass
        if fecha_hasta_raw:
            try:
                naive = dt.datetime.strptime(fecha_hasta_raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                notificaciones = notificaciones.filter(fecha__lte=tz.make_aware(naive))
            except ValueError:
                pass

    notificaciones = (
        notificaciones.select_related("id_usuario", "id_equipo_monitoreo__id_edificio")
        .distinct()
        .order_by("-fecha")
    )

    parsed_list = []
    for notif in notificaciones:
        notif = _parse_notif_for_historial(notif)
        parsed_list.append(notif)

    all_variables = sorted(set(
        n.parsed_data.get("variable", "")
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable")
    ))

    if variable_filter:
        parsed_list = [
            n for n in parsed_list
            if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable_filter
        ]

    paginator = Paginator(parsed_list, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    query_params = []
    if edificio_id:
        query_params.append(f"edificio={edificio_id}")
    if severidad:
        query_params.append(f"severidad={severidad}")
    if variable_filter:
        query_params.append(f"variable={variable_filter}")
    query_params.append(f"periodo={periodo_seleccionado}")
    if periodo_seleccionado == "custom":
        if fecha_desde_raw:
            query_params.append(f"fecha_desde={fecha_desde_raw}")
        if fecha_hasta_raw:
            query_params.append(f"fecha_hasta={fecha_hasta_raw}")
    filter_query_string = "&".join(query_params)

    return render(
        request,
        "monitoring/historial.html",
        {
            "notificaciones": page_obj,
            "edificios": edificios,
            "selected_edificio_id": int(edificio_id) if edificio_id and edificio_id.isdigit() else None,
            "severidad": severidad,
            "variable_filter": variable_filter,
            "all_variables": all_variables,
            "fecha_desde": fecha_desde_raw,
            "fecha_hasta": fecha_hasta_raw,
            "filter_query_string": filter_query_string,
            "ALL_SEVERITIES": ALL_SEVERITIES,
            "rol": rol,
            "total_count": len(parsed_list),
            "periodo_seleccionado": periodo_seleccionado,
        },
    )


# ─── CONTROL DEL SIMULADOR ──────────────────────────────────────


@_login_required
def simulador_status_view(request):
    from django.http import JsonResponse
    from apps.sensors.simulation import simulators
    has_edificios = Edificio.objects.exists()
    tiene_sim = len(simulators) > 0
    return JsonResponse({"running": tiene_sim, "has_edificios": has_edificios})


@_login_required
@_admin_required
def simulador_start_view(request):
    from django.http import JsonResponse
    from apps.sensors.simulation import simulators, BuildingSimulator
    from apps.buildings.models import EquipoMonitoreo
    if not simulators:
        _creados = 0
        for eq in EquipoMonitoreo.objects.select_related("id_edificio").all():
            if not eq.id_edificio:
                continue
            eid = eq.id_edificio.id_edificio
            enombre = eq.id_edificio.nb_edificio or f"Edificio #{eid}"
            if eid not in simulators:
                simulators[eid] = BuildingSimulator(eid, enombre)
            simulators[eid].equipment_types.add(eq.tipo)
            simulators[eid].has_pump = "bomba" in simulators[eid].equipment_types
            simulators[eid].has_elevator = "elevador" in simulators[eid].equipment_types
            simulators[eid].pump_on = simulators[eid].has_pump
            simulators[eid].elevator_on = simulators[eid].has_elevator
            _creados += 1
        if _creados:
            return JsonResponse({"status": "ok", "message": f"Simuladores creados ({_creados})."})
        return JsonResponse({"status": "error", "message": "No hay equipos de monitoreo en la BD."})
    for sim in simulators.values():
        sim.sim_paused = False
    return JsonResponse({"status": "ok", "message": "Simulación reanudada."})


@_login_required
@_admin_required
def simulador_stop_view(request):
    from django.http import JsonResponse
    from apps.sensors.simulation import simulators
    if not simulators:
        return JsonResponse({"status": "ok", "message": "No hay simuladores activos."})
    for sim in simulators.values():
        sim.sim_paused = True
    return JsonResponse({"status": "ok", "message": "Simulación pausada."})


@_login_required
@_admin_required
def simulador_restart_view(request):
    from django.http import JsonResponse
    from apps.sensors.simulation import simulators, reset_simulator
    if not simulators:
        return JsonResponse({"status": "error", "message": "No hay simuladores activos."})
    reiniciados = 0
    for eid in list(simulators.keys()):
        reset_simulator(eid)
        simulators[eid].sim_paused = False
        reiniciados += 1
    return JsonResponse({"status": "ok", "message": f"{reiniciados} simulador(es) reiniciado(s)."})
