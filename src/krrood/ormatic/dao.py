from __future__ import annotations

import abc
import inspect
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache

import sqlalchemy.inspection
import sqlalchemy.orm
from sqlalchemy import Column
from sqlalchemy.orm import MANYTOONE, ONETOMANY, RelationshipProperty
from typing_extensions import Optional, List
from typing_extensions import Type, get_args, Dict, Any, TypeVar, Generic, Self

from ..utils import recursive_subclasses

logger = logging.getLogger(__name__)
_repr_thread_local = threading.local()

T = TypeVar("T")
_DAO = TypeVar("_DAO", bound="DataAccessObject")
InstanceDict = Dict[int, Any]  # Dictionary that maps object ids to objects
InProgressDict = Dict[int, bool]


@dataclass
class NoGenericError(TypeError):
    """
    Exception raised when the original class for a DataAccessObject subclass cannot
    be determined.

    This exception is typically raised when a DataAccessObject subclass has not
    been parameterized properly, which prevents identifying the original class
    associated with it.
    """

    clazz: Type

    def __post_init__(self):
        super().__init__(
            f"Cannot determine original class for {self.clazz}. "
            "Did you forget to parameterise the DataAccessObject subclass?"
        )


@dataclass
class NoDAOFoundError(TypeError):
    """
    Represents an error raised when no DAO (Data Access Object) class is found for a given class.

    This exception is typically used when an attempt to convert a class into a corresponding DAO fails.
    It provides information about the class and the DAO involved.
    """

    obj: Any
    """
    The class that no dao was found for
    """

    def __post_init__(self):
        super().__init__(f"Class {type(self.obj)} does not have a DAO.")


@dataclass
class NoDAOFoundDuringParsingError(NoDAOFoundError):

    dao: Type
    """
    The DAO class that tried to convert the cls to a DAO if any.
    """

    relationship: RelationshipProperty
    """
    The relationship that tried to create the DAO.
    """

    def __init__(self, obj: Any, dao: Type, relationship: RelationshipProperty = None):
        TypeError.__init__(
            self,
            f"Class {type(obj)} does not have a DAO. This happened when trying"
            f"to create a dao for {dao}) on the relationship {relationship} with the "
            f"relationship value {obj}."
            f"Expected a relationship value of type {relationship.target}.",
        )


def is_data_column(column: Column):
    return (
        not column.primary_key
        and len(column.foreign_keys) == 0
        and column.name != "polymorphic_type"
    )


class HasGeneric(Generic[T]):

    @classmethod
    @lru_cache(maxsize=None)
    def original_class(cls) -> T:
        """
        :return:The concrete generic argument for DAO-like bases. Raises and Error if None are found.
        """
        tp = cls._dao_like_argument()
        if tp is None:
            raise NoGenericError(cls)
        return tp

    @classmethod
    def _dao_like_argument(cls) -> Optional[Type]:
        """
        :return: The concrete generic argument for DAO-like bases.
        """
        # Prefer an explicit DAO origin if present
        for base in getattr(cls, "__orig_bases__", []):
            origin = getattr(base, "__origin__", None)
            if origin is DataAccessObject or origin is AlternativeMapping:
                args = get_args(base)
                if args:
                    return args[0]
        # No acceptable base found
        return None


@dataclass
class UnsupportedRelationshipError(ValueError):
    """
    Raised when a relationship direction is not supported by the ORM mapping.

    This error indicates that the relationship configuration could not be
    interpreted into a domain mapping.
    """

    relationship: RelationshipProperty

    def __post_init__(self):
        ValueError.__init__(
            self,
            f"Unsupported relationship direction for {self.relationship}.",
        )


class DataAccessObject(HasGeneric[T]):
    """
    This class defines the interfaces the DAO classes should implement.

    ORMatic generates classes from your python code that are derived from the provided classes in your package.
    The generated classes can be instantiated from objects of the given classes and vice versa.
    This class implements the necessary functionality.
    """

    @classmethod
    def to_dao(
        cls,
        obj: T,
        memo: InstanceDict = None,
        keep_alive: InstanceDict = None,
        register=True,
    ) -> _DAO:
        """
        Convert an object to its Data Access Object.

        Ensures memoization to prevent duplicate work, applies alternative
        mappings when needed, and delegates to the appropriate conversion
        strategy based on inheritance.

        :param obj: Object to be converted into its DAO equivalent
        :param memo: Dictionary that keeps track of already converted objects to avoid duplicate processing.
            Defaults to None.
        :param keep_alive: Dictionary to keep track of objects that should not be garbage collected during the conversion.
            Defaults to None.
        :param register: Whether to register the DAO class in the memo.
        :return: Instance of the DAO class (_DAO) that represents the input object after conversion
        """

        memo, keep_alive = cls._ensure_memo_dicts(memo, keep_alive)

        # check if this object has been build already
        existing = memo.get(id(obj))
        if existing is not None:
            return existing

        dao_obj = cls._apply_alternative_mapping_if_needed(obj, memo, keep_alive)

        base = cls.__bases__[0]
        result = cls()

        if register:
            cls._register_in_memo(memo, keep_alive, obj, result)

        # chose the correct building method
        if cls.uses_alternative_mapping(base):
            result.to_dao_if_subclass_of_alternative_mapping(
                obj=dao_obj, memo=memo, keep_alive=keep_alive, base=base
            )
        else:
            result.to_dao_default(obj=dao_obj, memo=memo, keep_alive=keep_alive)

        return result

    @classmethod
    def uses_alternative_mapping(cls, class_to_check: Type) -> bool:
        """
        :param class_to_check: The class to check
        :return: If the class to check uses an alternative mapping to specify the DAO or not.
        """
        return issubclass(class_to_check, DataAccessObject) and issubclass(
            class_to_check.original_class(), AlternativeMapping
        )

    @classmethod
    def _ensure_memo_dicts(
        cls, memo: Optional[InstanceDict], keep_alive: Optional[InstanceDict]
    ) -> tuple[InstanceDict, InstanceDict]:
        """
        Ensure memo and keep_alive dictionaries exist.
        :return: (memo, keep_alive)
        """
        return (memo or {}), (keep_alive or {})

    @classmethod
    def _apply_alternative_mapping_if_needed(
        cls, obj: T, memo: Dict[int, Any], keep_alive: Dict[int, Any]
    ) -> Any:
        """
        :return: An object or its alternative mapped DAO if required by the class.
        """
        if issubclass(cls.original_class(), AlternativeMapping):
            return cls.original_class().to_dao(obj, memo=memo, keep_alive=keep_alive)
        return obj

    @classmethod
    def _register_in_memo(
        cls, memo: Dict[int, Any], keep_alive: Dict[int, Any], obj: Any, result: Any
    ) -> None:
        """
        Register a partially built DAO in memoization stores to break cycles.
        """
        original_obj_id = id(obj)
        memo[original_obj_id] = result
        keep_alive[original_obj_id] = obj

    def to_dao_default(self, obj: T, memo: InstanceDict, keep_alive: InstanceDict):
        """
        Converts the given object into a Data Access Object (DAO) representation
        by extracting column and relationship data. This method is primarily used
        in ORM to transform a domain object into its mapped
        database representation.

        :param obj: The source object to be converted into a DAO representation.
        :param memo: A dictionary to handle cyclic references by tracking processed objects.
        :param keep_alive: A dictionary to keep track of objects that should not be garbage collected during the conversion
        """
        # Fill super class columns, Mapper-columns - self.columns
        mapper: sqlalchemy.orm.Mapper = sqlalchemy.inspection.inspect(type(self))

        # Create a new instance of the DAO class
        self.get_columns_from(obj=obj, columns=mapper.columns)
        self.get_relationships_from(
            obj=obj,
            relationships=mapper.relationships,
            memo=memo,
            keep_alive=keep_alive,
        )

    def to_dao_if_subclass_of_alternative_mapping(
        self,
        obj: T,
        memo: Dict[int, Any],
        keep_alive: Dict[int, Any],
        base: Type[DataAccessObject],
    ):
        """
        Transforms the given object into a corresponding DAO if it is a
        subclass of an alternatively mapped entity. This involves processing both the inherited
        and subclass-specific attributes and relationships of the object.
        The method directly modifies the DAO instance by populating it with attribute
        and relationship data from the source object.

        :param obj: The source object to be transformed into a DAO.
        :param memo: A dictionary used to handle circular references when transforming objects.
                     Typically acts as a memoization structure for keeping track of processed objects.
        :param keep_alive: A dictionary to ensure that objects remain in memory during the transformation
                          process, preventing them from being garbage collected prematurely.
        :param base: The parent class type that defines the base mapping for the DAO.
        """

        # Temporarily remove the object from the memo dictionary to allow the parent DAO to be created
        temp_dao = None
        if id(obj) in memo:
            temp_dao = memo[id(obj)]
            del memo[id(obj)]

        # create dao of alternatively mapped superclass
        parent_dao = base.original_class().to_dao(obj, memo=memo, keep_alive=keep_alive)

        # Restore the object in the memo dictionary
        if temp_dao is not None:
            memo[id(obj)] = temp_dao

        # Fill super class columns
        parent_mapper = sqlalchemy.inspection.inspect(base)
        mapper: sqlalchemy.orm.Mapper = sqlalchemy.inspection.inspect(type(self))

        # split up the columns in columns defined by the parent and columns defined by this dao
        all_columns = mapper.columns
        columns_of_parent = parent_mapper.columns
        columns_of_this_table = [
            c for c in all_columns if c.name not in columns_of_parent
        ]

        # copy values from superclass dao
        self.get_columns_from(parent_dao, columns_of_parent)

        # copy values that only occur in this dao
        self.get_columns_from(obj, columns_of_this_table)

        # split relationships in relationships by parent and relationships by child
        all_relationships = mapper.relationships
        relationships_of_parent = parent_mapper.relationships
        relationships_of_this_table = [
            r for r in all_relationships if r not in relationships_of_parent
        ]

        for relationship in relationships_of_parent:
            setattr(self, relationship.key, getattr(parent_dao, relationship.key))

        self.get_relationships_from(obj, relationships_of_this_table, memo, keep_alive)

    def get_columns_from(self, obj: T, columns: List):
        """
        Retrieves and assigns values from specified columns of a given object.

        Assumes that the attribute names of `obj` and `self` are the same.

        :param obj: The object from which the column values are retrieved.
        :param columns: A list of columns to be processed.

        Raises:
            AttributeError: Raised if the provided object or column does not have
                the corresponding attribute during assignment.
        """
        for column in columns:
            if is_data_column(column):
                setattr(self, column.name, getattr(obj, column.name))

    def get_relationships_from(
        self,
        obj: T,
        relationships: List[RelationshipProperty],
        memo: Dict[int, Any],
        keep_alive: Dict[int, Any],
    ):
        """
        Retrieve and update relationships from an object based on the given relationship
        properties.

        This method delegates to focused helpers for single-valued and collection-valued
        relationships to keep complexity low.

        :param obj: The object from which the relationship values are retrieved.
        :param relationships: A list of relationships to be processed.
        :param memo: A dictionary used to handle circular references when transforming objects.
        :param keep_alive: A dictionary to ensure that objects remain in memory during the transformation
        """
        for relationship in relationships:
            if relationship.direction == MANYTOONE or (
                relationship.direction == ONETOMANY and not relationship.uselist
            ):
                self._extract_single_relationship(
                    obj=obj,
                    relationship=relationship,
                    memo=memo,
                    keep_alive=keep_alive,
                )
            elif relationship.direction == ONETOMANY:
                self._extract_collection_relationship(
                    obj=obj,
                    relationship=relationship,
                    memo=memo,
                    keep_alive=keep_alive,
                )

    def _extract_single_relationship(
        self,
        obj: T,
        relationship: RelationshipProperty,
        memo: InstanceDict,
        keep_alive: InstanceDict,
    ) -> None:
        """
        Extract a single-valued relationship and assign the corresponding DAO.
        Check `get_relationships_from` for more information.
        """
        value_in_obj = getattr(obj, relationship.key)
        if value_in_obj is None:
            setattr(self, relationship.key, None)
            return

        dao_class = get_dao_class(type(value_in_obj))
        if dao_class is None:
            raise NoDAOFoundDuringParsingError(value_in_obj, type(self), relationship)

        dao_of_value = dao_class.to_dao(value_in_obj, memo=memo, keep_alive=keep_alive)
        setattr(self, relationship.key, dao_of_value)

    def _extract_collection_relationship(
        self,
        obj: T,
        relationship: RelationshipProperty,
        memo: InstanceDict,
        keep_alive: InstanceDict,
    ) -> None:
        """
        Extract a collection-valued relationship and assign a list of DAOs.
        Check `get_relationships_from` for more information.
        """
        result = []
        value_in_obj = getattr(obj, relationship.key)
        for v in value_in_obj:
            dao_class = get_dao_class(type(v))
            if dao_class is None:
                raise NoDAOFoundDuringParsingError(v, type(self), relationship)
            result.append(dao_class.to_dao(v, memo=memo, keep_alive=keep_alive))
        setattr(self, relationship.key, result)

    def from_dao(
        self,
        memo: Optional[InstanceDict] = None,
        in_progress: Optional[InProgressDict] = None,
    ) -> T:
        """
        Convert this Data Access Object into its domain model instance.

        Uses a two-phase approach: allocate and memoize first to break cycles,
        then populate scalars and relationships, handle alternative mapping
        inheritance, initialize, and finally fix circular references.

        :param memo: A dictionary used to handle circular references when transforming objects.
        :param in_progress: A dictionary to flag objects as currently being processed.
        """
        memo, in_progress = self._ensure_from_dao_state(memo, in_progress)

        if id(self) in memo:
            return memo[id(self)]

        result = self._allocate_uninitialized_and_memoize(memo, in_progress)
        mapper: sqlalchemy.orm.Mapper = sqlalchemy.inspection.inspect(type(self))

        argument_names = self._argument_names()
        kwargs = self._collect_scalar_kwargs(mapper, argument_names)

        rel_kwargs, circular_refs = self._collect_relationship_kwargs(
            mapper, argument_names, memo, in_progress
        )
        kwargs.update(rel_kwargs)

        base_kwargs = self._build_base_kwargs_for_alternative_parent(
            argument_names, memo, in_progress
        )

        init_args = {**base_kwargs, **kwargs}
        self._call_initializer_or_assign(result, init_args)

        self._apply_circular_fixes(result, circular_refs, memo)

        if isinstance(result, AlternativeMapping):
            result = result.create_from_dao()
            memo[id(self)] = result

        del in_progress[id(self)]
        return result

    @classmethod
    def _ensure_from_dao_state(
        cls, memo: Optional[InstanceDict], in_progress: Optional[InProgressDict]
    ) -> tuple[InstanceDict, InProgressDict]:
        """
        Ensure required state dictionaries exist for from_dao execution.
        """
        return (memo or {}), (in_progress or {})

    def _allocate_uninitialized_and_memoize(
        self, memo: InstanceDict, in_progress: InProgressDict
    ) -> Any:
        """
        Allocate an uninitialized domain object and memoize immediately.
        """
        result = self.original_class().__new__(self.original_class())
        memo[id(self)] = result
        in_progress[id(self)] = True
        return result

    def _argument_names(self) -> List[str]:
        """
        :return: __init__ argument names of the original class (excluding self).
        """
        init_of_original_class = self.original_class().__init__
        return [
            p.name
            for p in inspect.signature(init_of_original_class).parameters.values()
        ][1:]

    def _collect_scalar_kwargs(
        self, mapper: sqlalchemy.orm.Mapper, argument_names: List[str]
    ) -> Dict[str, Any]:
        """
        :return: keyword arguments for scalar columns present in the constructor.
        """
        kwargs: Dict[str, Any] = {}
        for column in mapper.columns:
            if column.name in argument_names and is_data_column(column):
                kwargs[column.name] = getattr(self, column.name)
        return kwargs

    def _collect_relationship_kwargs(
        self,
        mapper: sqlalchemy.orm.Mapper,
        argument_names: List[str],
        memo: InstanceDict,
        in_progress: InProgressDict,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Collect relationship constructor arguments and capture circular references.

        :param mapper: SQLAlchemy mapper object
        :param argument_names: Names of arguments
        :param memo: Dictionary used to handle circular references when transforming objects.
        :param in_progress: Dictionary used to handle circular references when transforming objects.
        :return: A tuple of (relationship_kwargs, circular_references_map).
        """
        rel_kwargs: Dict[str, Any] = {}
        circular_refs: Dict[str, Any] = {}
        for relationship in mapper.relationships:
            if relationship.key not in argument_names:
                continue
            value = getattr(self, relationship.key)
            if relationship.direction == MANYTOONE or (
                relationship.direction == ONETOMANY and not relationship.uselist
            ):
                parsed, is_circular = self._parse_single_relationship_value(
                    value, memo, in_progress
                )
                if is_circular:
                    circular_refs[relationship.key] = value
                rel_kwargs[relationship.key] = parsed
            elif relationship.direction == ONETOMANY:
                parsed_list, circular_list = self._parse_collection_relationship(
                    value, memo, in_progress
                )
                if circular_list:
                    circular_refs[relationship.key] = circular_list
                rel_kwargs[relationship.key] = parsed_list
            else:
                raise UnsupportedRelationshipError(relationship)
        return rel_kwargs, circular_refs

    @classmethod
    def _parse_single_relationship_value(
        cls, value: Any, memo: InstanceDict, in_progress: InProgressDict
    ) -> tuple[Any, bool]:
        """
        Parse a single-valued relationship DAO into a domain object.

        :return: The parsed object and whether a circular reference placeholder was detected.
        """
        if value is None:
            return None, False
        parsed = value.from_dao(memo=memo, in_progress=in_progress)
        return parsed, parsed is memo.get(id(value))

    @classmethod
    def _parse_collection_relationship(
        cls, value: Any, memo: InstanceDict, in_progress: InProgressDict
    ) -> tuple[Any, List[Any]]:
        """
        Parse a collection-valued relationship DAO list into domain objects.

        :return: A tuple of (parsed_collection_of_same_type_as_input, circular_values_list).
        """
        if not value:
            return value, []
        instances = []
        circular_values: List[Any] = []
        for v in value:
            instance = v.from_dao(memo=memo, in_progress=in_progress)
            if instance is memo.get(id(v)):
                circular_values.append(v)
            instances.append(instance)
        return type(value)(instances), circular_values

    def _build_base_kwargs_for_alternative_parent(
        self,
        argument_names: List[str],
        memo: InstanceDict,
        in_progress: InProgressDict,
    ) -> Dict[str, Any]:
        """
        Build a dictionary of base keyword arguments for an alternative parent DAO and mapping.

        This method constructs and returns a set of keyword arguments by inspecting the base
        class. If the base class is a DataAccessObject and supports an AlternativeMapping,
        data columns and relationships of the parent DAO are copied and converted using its
        `from_dao` method.

        :param argument_names: The list of argument names to include in the dictionary if
            they exist in the base result but are not already present as attributes of the
            current instance.

        :param memo: A memoization dictionary used during object conversion.
        :param in_progress: A dictionary tracking the state of objects currently being
            processed.
        :return: A dictionary of keyword arguments derived from the base DAO and mapping.
        """
        base = self.__class__.__bases__[0]
        base_kwargs: Dict[str, Any] = {}
        if issubclass(base, DataAccessObject) and issubclass(
            base.original_class(), AlternativeMapping
        ):
            parent_dao = base()
            parent_mapper = sqlalchemy.inspection.inspect(base)
            for column in parent_mapper.columns:
                if is_data_column(column):
                    setattr(parent_dao, column.name, getattr(self, column.name))
            for rel in parent_mapper.relationships:
                setattr(parent_dao, rel.key, getattr(self, rel.key))
            base_result = parent_dao.from_dao(memo=memo, in_progress=in_progress)
            for argument in argument_names:
                if argument not in base_kwargs and not hasattr(self, argument):
                    try:
                        base_kwargs[argument] = getattr(base_result, argument)
                    except AttributeError:
                        ...
        return base_kwargs

    @classmethod
    def _call_initializer_or_assign(
        cls, result: Any, init_args: Dict[str, Any]
    ) -> None:
        """
        Call the original __init__. If it fails due to signature mismatch, assign attributes directly.
        """
        try:
            result.__init__(**init_args)
        except TypeError as e:
            logging.getLogger(__name__).debug(
                f"from_dao __init__ call failed with {e}; falling back to manual assignment. "
                f"This might skip side effects of the original initialization."
            )
            for key, val in init_args.items():
                setattr(result, key, val)

    @classmethod
    def _apply_circular_fixes(
        cls, result: Any, circular_refs: Dict[str, Any], memo: InstanceDict
    ) -> None:
        """
        Replace circular placeholder DAOs with their finalized domain objects.
        """
        for key, value in circular_refs.items():
            if isinstance(value, list):
                fixed_list = []
                for v in value:
                    fixed = memo.get(id(v))
                    fixed_list.append(fixed)
                setattr(result, key, fixed_list)
            else:
                fixed = memo.get(id(value))
                setattr(result, key, fixed)

    def __repr__(self):
        if not hasattr(_repr_thread_local, "seen"):
            _repr_thread_local.seen = set()

        if id(self) in _repr_thread_local.seen:
            return f"{self.__class__.__name__}(...)"

        _repr_thread_local.seen.add(id(self))
        try:
            mapper: sqlalchemy.orm.Mapper = sqlalchemy.inspection.inspect(type(self))
            kwargs = []
            for column in mapper.columns:
                value = getattr(self, column.name)
                if is_data_column(column):
                    kwargs.append(f"{column.name}={repr(value)}")

            for relationship in mapper.relationships:
                value = getattr(self, relationship.key)
                if value is not None:
                    if isinstance(value, list):
                        kwargs.append(
                            f"{relationship.key}=[{', '.join(repr(v) for v in value)}]"
                        )
                    else:
                        kwargs.append(f"{relationship.key}={repr(value)}")
                else:
                    kwargs.append(f"{relationship.key}=None")

            return f"{self.__class__.__name__}({', '.join(kwargs)})"
        finally:
            _repr_thread_local.seen.remove(id(self))


class AlternativeMapping(HasGeneric[T], abc.ABC):

    @classmethod
    def to_dao(
        cls, obj: T, memo: Dict[int, Any] = None, keep_alive: Dict[int, Any] = None
    ) -> _DAO:
        """
        Create a DAO from the obj if it doesn't exist.

        :param obj: The obj to create the DAO from.
        :param memo: The memo dictionary to check for already build instances.
        :param keep_alive: The keep_alive dictionary to keep the object alive during the conversion.

        :return: An instance of this class created from the obj.
        """
        if memo is None:
            memo = {}
        if id(obj) in memo:
            return memo[id(obj)]
        elif isinstance(obj, cls):
            return obj
        else:
            result = cls.create_instance(obj)
            # memo[id(obj)] = result
            return result

    @classmethod
    @abc.abstractmethod
    def create_instance(cls, obj: T) -> Self:
        """
        Create a DAO from the obj.
        The method needs to be overloaded by the user.

        :param obj: The obj to create the DAO from.
        :return: An instance of this class created from the obj.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def create_from_dao(self) -> T:
        """
        Creates an object from a Data Access Object (DAO) by utilizing the predefined
        logic and transformations specific to the implementation. This facilitates
        constructing domain-specific objects from underlying data representations.

        :return: The object created from the DAO.
        :rtype: T
        """
        raise NotImplementedError


@lru_cache(maxsize=None)
def get_dao_class(cls: Type) -> Optional[Type[DataAccessObject]]:
    if get_alternative_mapping(cls) is not None:
        cls = get_alternative_mapping(cls)
    for dao in recursive_subclasses(DataAccessObject):
        if dao.original_class() == cls:
            return dao
    return None


@lru_cache(maxsize=None)
def get_alternative_mapping(cls: Type) -> Optional[Type[DataAccessObject]]:
    for alt_mapping in recursive_subclasses(AlternativeMapping):
        if alt_mapping.original_class() == cls:
            return alt_mapping
    return None


def to_dao(
    obj: Any, memo: Dict[int, Any] = None, keep_alive: Dict[int, Any] = None
) -> DataAccessObject:
    """
    Convert any object to a dao class.

    :param obj: The object to convert to a dao.
    :param memo: A dictionary to keep track of already converted objects.
    :param keep_alive: A dictionary to keep the object alive during the conversion.
    """
    dao_class = get_dao_class(type(obj))
    if dao_class is None:
        raise NoDAOFoundError(type(obj))
    return dao_class.to_dao(obj, memo, keep_alive)
