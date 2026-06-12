from dataclasses import dataclass, field

from apps.buildings.models import Building, MonitoringEquipment


@dataclass
class EquipmentConfig:
    has_pump: bool = False
    has_elevator: bool = False


def create_equipment_for_building(
    building: Building,
    config: EquipmentConfig,
) -> None:
    if config.has_pump:
        MonitoringEquipment.objects.get_or_create(
            building=building, equipment_type=MonitoringEquipment.TYPE_PUMP,
            defaults={"name": f"Bomba de agua - {building.name}"},
        )
    if config.has_elevator:
        MonitoringEquipment.objects.get_or_create(
            building=building, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
            defaults={"name": f"Elevador - {building.name}"},
        )


def sync_equipment_for_building(
    building: Building,
    config: EquipmentConfig,
) -> None:
    if config.has_pump:
        MonitoringEquipment.objects.get_or_create(
            building=building, equipment_type=MonitoringEquipment.TYPE_PUMP,
            defaults={"name": f"Bomba de agua - {building.name}"},
        )
    else:
        MonitoringEquipment.objects.filter(
            building=building, equipment_type=MonitoringEquipment.TYPE_PUMP,
        ).delete()
    if config.has_elevator:
        MonitoringEquipment.objects.get_or_create(
            building=building, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
            defaults={"name": f"Elevador - {building.name}"},
        )
    else:
        MonitoringEquipment.objects.filter(
            building=building, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
        ).delete()
