# Dealing with unmappable dataclasses

ORMatic can infer a mapping for a dataclass from its fields and relationships. This is the default behavior.
However, sometimes you may need to customize the mapping. There are two ways to do this:

## Type Decorators
You can provide the ormatic a type mapping that maps a Python type to a (SQLAlchemy TypeDecorator)[https://docs.sqlalchemy.org/en/20/core/custom_types.html.
This decorator is then used as a type mapping everytime ormatic encounters the type.
I recommend using this approach when dealing with meshes, numpy arrays, etc. Basically anything
that does not contain any fields that need to be referenced by other classes.

## Alternative Mapping (Explicit Control)
If a dataclass does not fit the standard rules or requires a more specialized schema, 
define an explicit mapping by subclassing the relevant mapping base 
(see tests for `AlternativeMapping` usage) and include that mapping in the class set you pass to ORMatic. 
This lets you:
- Override column names or shapes
- Introduce association tables explicitly
- Write reusable mappings that can be shared across multiple applications
- Filter information that should not persist
