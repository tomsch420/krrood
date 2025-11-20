from __future__ import annotations

import importlib
from dataclasses import dataclass

from typing_extensions import Dict, Any, Self
import json
import uuid


def get_full_class_name(cls):
    """
    Returns the full name of a class, including the module name.

    :param cls: The class.
    :return: The full name of the class
    """
    return cls.__module__ + "." + cls.__name__


class JSONSerializationError(Exception):
    """Base exception for JSON (de)serialization errors."""


class MissingTypeError(JSONSerializationError):
    """Raised when the 'type' field is missing in the JSON data."""

    def __init__(self):
        super().__init__("Missing 'type' field in JSON data")


@dataclass
class InvalidTypeFormatError(JSONSerializationError):
    """Raised when the 'type' field value is not a fully qualified class name."""

    invalid_type_value: str

    def __post_init__(self):
        super().__init__(f"Invalid type format: {self.invalid_type_value}")


@dataclass
class UnknownModuleError(JSONSerializationError):
    """Raised when the module specified in the 'type' field cannot be imported."""

    module_name: str

    def __post_init__(self):
        super().__init__(f"Unknown module in type: {self.module_name}")


@dataclass
class ClassNotFoundError(JSONSerializationError):
    """Raised when the class specified in the 'type' field cannot be found in the module."""

    class_name: str
    module_name: str

    def __post_init__(self):
        super().__init__(
            f"Class '{self.class_name}' not found in module '{self.module_name}'"
        )


@dataclass
class InvalidSubclassError(JSONSerializationError):
    """Raised when the resolved class is not a SubclassJSONSerializer subclass."""

    fully_qualified_class_name: str

    def __post_init__(self):
        super().__init__(
            f"Resolved type {self.fully_qualified_class_name} is not a SubclassJSONSerializer"
        )


class SubclassJSONSerializer:
    """
    Class for automatic (de)serialization of subclasses using importlib.

    Stores the fully qualified class name in `type` during serialization and
    imports that class during deserialization.
    """

    def to_json(self) -> Dict[str, Any]:
        return {"type": get_full_class_name(self.__class__)}

    @classmethod
    def _from_json(cls, data: Dict[str, Any], **kwargs) -> Self:
        """
        Create an instance from a json dict.
        This method is called from the from_json method after the correct subclass is determined and should be
        overwritten by the subclass.

        :param data: The json dict
        :param kwargs: Additional keyword arguments to pass to the constructor of the subclass.
        :return: The deserialized object
        """
        raise NotImplementedError()

    @classmethod
    def from_json(cls, data: Dict[str, Any], **kwargs) -> Self:
        """
        Create the correct instanceof the subclass from a json dict.

        :param data: The json dict
        :param kwargs: Additional keyword arguments to pass to the constructor of the subclass.
        :return: The correct instance of the subclass
        """
        fully_qualified_class_name = data.get("type")
        if not fully_qualified_class_name:
            raise MissingTypeError()

        try:
            module_name, class_name = fully_qualified_class_name.rsplit(".", 1)
        except ValueError as exc:
            raise InvalidTypeFormatError(fully_qualified_class_name) from exc

        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise UnknownModuleError(module_name) from exc

        try:
            target_cls = getattr(module, class_name)
        except AttributeError as exc:
            raise ClassNotFoundError(class_name, module_name) from exc

        # if not issubclass(target_cls, SubclassJSONSerializer):
        #   raise InvalidSubclassError(fully_qualified_class_name)

        return target_cls._from_json(data, **kwargs)


class SubclassJSONEncoder(json.JSONEncoder):
    """
    Custom encoder to handle classes that inherit from SubClassJSONEncoder and UUIDs.
    """

    def default(self, obj):
        if isinstance(obj, SubclassJSONSerializer):
            return obj.to_json()

        elif isinstance(obj, uuid.UUID):
            # Convert the UUID to its string representation
            return uuid_to_json(obj)
        # Let the base class handle other objects
        return json.JSONEncoder.default(self, obj)


class SubclassJSONDecoder(json.JSONDecoder):

    def decode(self, s, _w=json.decoder.WHITESPACE.match):
        obj = super().decode(s, _w)
        # Custom logic: Convert all dicts that containing a type using the SubClassJSONSerializer.from_json method
        if "type" in obj:
            obj = SubclassJSONSerializer.from_json(obj)
        else:
            return obj
        return obj


# %% Monkey patch UUID to behave like SubClassJSONSerializer
def uuid_from_json(data):
    return uuid.UUID(data["value"])


def uuid_to_json(obj):
    return {"type": get_full_class_name(obj.__class__), "value": str(obj)}


uuid.UUID._from_json = lambda data: uuid_from_json(data)
uuid.UUID.to_json = lambda self: uuid_to_json(self)
