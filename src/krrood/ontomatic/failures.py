from __future__ import annotations

from dataclasses import dataclass


@dataclass(init=False)
class UnMonitoredContainerTypeForDescriptor(Exception):
    """
    Raised when a descriptor is used on a field with a container type that is not monitored (i.e., is not a subclass of
    MonitoredContainer). This happens when your type hint of the field is using a container type that is not supported.
    """

    clazz: type
    field_name: str
    container_type: type

    def __init__(self, clazz: type, field_name: str, container_type: type):
        self.clazz = clazz
        self.field_name = field_name
        self.container_type = container_type
        super().__init__(
            f"Unmonitored container type '{container_type.__name__}' used for field '{field_name}' "
            f"in class '{clazz.__name__}'."
        )
