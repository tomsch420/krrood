from __future__ import annotations

import importlib
from abc import abstractmethod
from functools import lru_cache
from typing import Type, List

from typing_extensions import Dict, Any, Self


@lru_cache(maxsize=None)
def recursive_subclasses(cls: Type) -> List[Type]:
    """
    :param cls: The class.
    :return: A list of the classes subclasses without the class itself.
    """
    return cls.__subclasses__() + [
        g for s in cls.__subclasses__() for g in recursive_subclasses(s)
    ]


def get_full_class_name(cls):
    """
    Returns the full name of a class, including the module name.

    :param cls: The class.
    :return: The full name of the class
    """
    return cls.__module__ + "." + cls.__name__


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
        fqcn = data.get("type")
        if not fqcn:
            raise ValueError("Missing 'type' in JSON data")

        try:
            module_name, class_name = fqcn.rsplit(".", 1)
        except ValueError as exc:
            raise ValueError(f"Invalid type format: {fqcn}") from exc

        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise ValueError(f"Unknown module in type: {module_name}") from exc

        try:
            target_cls = getattr(module, class_name)
        except AttributeError as exc:
            raise ValueError(
                f"Class '{class_name}' not found in module '{module_name}'"
            ) from exc

        if not issubclass(target_cls, SubclassJSONSerializer):
            raise TypeError(f"Resolved type {fqcn} is not a SubclassJSONSerializer")

        return target_cls._from_json(data, **kwargs)
