### Practical Tips and Best Practices
- Model with dataclasses first. Use small, value-oriented dataclasses, and let ORMatic discover relationships from nesting and lists.
- Keep collections simple. Use `list[T]` or `set[T]` and avoid nested collections.
- Use default factories. When a collection may be empty, define `field(default_factory=list)` or similar.
- Keep Optionals minimal. If a field can be absent, make it `Optional[T]`. For richer alternatives, consider separate subclasses.
- Make inheritance intentional. Put the “queryable” base class first in multiple inheritance to align polymorphic behavior with your expectations.
- Prefer explicit mappings when integrating with an existing database schema that does not match your domain shape.

### Limitations and Known Caveats
- Complex union types beyond `Optional[T]` are not supported. Model alternatives via subtyping.
- Optional or nested collections are not supported.
- Certain polymorphic base queries may require querying concrete DAOs; this depends on your inheritance tree and SQLAlchemy behavior.

### Frequently Asked Questions
- How do I exclude a field? Prefix it with `_`, for example `_cache: dict = field(default_factory=dict)`.
- How do I add a custom type? Register an appropriate SQLAlchemy `TypeDecorator` and include it in the generated `Base.type_mappings`, or wrap the type in its own dataclass and let ORMatic map it as a nested object.
- Can I keep my domain free of SQLAlchemy imports? Yes. The generated file is the only place that depends on SQLAlchemy.
- Can I mix explicit and implicit mappings? Yes. Explicit mappings override inferred ones for the same domain class.

### Troubleshooting Checklist
- Getting `NoDAOFoundError` when persisting: Did you include the class (or its mapping) in the set passed to `ORMatic`? Did you filter out `Enum` and non-dataclass types correctly?
- Collection fields not being created: Verify that the element type is a mapped dataclass and that the collection is not optional.
- Circular references fail to reconstruct: Ensure both ends of the relation are included in the mapping set and that backreferences are dataclass fields (not runtime-only `_` fields).
