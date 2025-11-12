from __future__ import annotations


class UnMonitoredContainerTypeForDescriptor(Exception):
    """
    Raised when a descriptor is used on a field with a container type that is not monitored (i.e., is not a subclass of
    MonitoredContainer).
    """

    ...
