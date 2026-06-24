class SimulatorError(Exception):


    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SimulatorNotFoundError(SimulatorError):
    def __init__(self, edificio_id: int):
        super().__init__(f"Edificio {edificio_id} no encontrado", status_code=404)


class InvalidDeviceError(SimulatorError):
    def __init__(self, device: str):
        _ES = {"pump": "Bomba", "elevator": "Elevador"}
        super().__init__(f"Dispositivo no válido: {_ES.get(device, device)}")


class DeviceNotInBuildingError(SimulatorError):
    def __init__(self, device: str):
        _ES = {"pump": "Bomba", "elevator": "Elevador"}
        super().__init__(f"El edificio no tiene {_ES.get(device, device)}")


class InvalidFaultTypeError(SimulatorError):
    def __init__(self, device: str, fault_type: str):
        from apps.sensors.sensor_config import FAULT_NAMES_ES
        _DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}
        nombre_falla = FAULT_NAMES_ES.get(fault_type, fault_type)
        nombre_dispositivo = _DEVICE_ES.get(device, device)
        super().__init__(f"Falla '{nombre_falla}' no es válida para {nombre_dispositivo}")


class NoSimulatorAvailableError(SimulatorError):
    def __init__(self):
        super().__init__("No hay simuladores activos disponibles")
