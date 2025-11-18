import importlib
from dataclasses import dataclass
from typing import Self

from collections.abc import Callable
from typing_extensions import Optional

from .dao import AlternativeMapping, T
from ..utils import Function


@dataclass
class FunctionMapping(AlternativeMapping[Function]):

    module_name: str
    """
    The module name where the function is defined.
    """

    function_name: str
    """
    The name of the function.
    """

    class_name: Optional[str] = None
    """
    The name of the class if the function is defined by a class.
    """

    @classmethod
    def create_instance(cls, obj: Callable) -> Self:

        if "." in obj.__qualname__:
            class_name = obj.__qualname__.split(".")[0]
        else:
            class_name = None
        dao = cls(
            module_name=obj.__module__,
            function_name=obj.__name__,
            class_name=class_name,
        )
        return dao

    def create_from_dao(self) -> T:

        if self.function_name == "<lambda>":
            return lambda *args: NotImplementedError()

        module = importlib.import_module(self.module_name)

        if self.class_name is not None:
            return getattr(getattr(module, self.class_name), self.function_name)
        else:
            return getattr(module, self.function_name)
