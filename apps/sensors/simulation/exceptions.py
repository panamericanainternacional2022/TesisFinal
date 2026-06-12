class SimulatorError(Exception):
    """Base exception for simulator operations."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SimulatorNotFoundError(SimulatorError):
    def __init__(self, edificio_id: int):
        super().__init__(f"Edificio {edificio_id} no encontrado", status_code=404)


class InvalidDeviceError(SimulatorError):
    def __init__(self, device: str):
        super().__init__(f"Dispositivo debe ser 'pump' o 'elevator': {device}")


class DeviceNotInBuildingError(SimulatorError):
    def __init__(self, device: str):
        super().__init__(f"El edificio no tiene {device}")


class InvalidFaultTypeError(SimulatorError):
    def __init__(self, device: str, fault_type: str):
        super().__init__(f"Falla inválida para {device}: {fault_type}")


class NoSimulatorAvailableError(SimulatorError):
    def __init__(self):
        super().__init__("No hay simuladores activos disponibles")
