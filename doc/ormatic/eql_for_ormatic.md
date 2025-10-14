# Using Entity Query Language (EQL) With ORMatic
ORMatic can translate high-level EQL expressions into SQLAlchemy `select(...)` statements.

- Build expressions over variables that carry the underlying Python type.
- Use `eql_to_sql(expr)` to get a SQLAlchemy statement and execute it with your session.

Example:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers

from entity_query_language.entity import let
from entity_query_language import or_, in_

from classes.example_classes import Position
from classes.sqlalchemy_interface import Base, PositionDAO

from ormatic.eql_interface import eql_to_sql

configure_mappers()
engine = create_engine('sqlite:///:memory:')
session = Session(engine)
Base.metadata.create_all(engine)

# Insert sample data
session.add_all([
    PositionDAO.to_dao(Position(1, 2, 3)),
    PositionDAO.to_dao(Position(1, 2, 4)),
    PositionDAO.to_dao(Position(2, 9, 10)),
])
session.commit()

# Build an EQL expression
position = let(type_=Position, domain=[Position(0, 0, 0)])  # domain is irrelevant for translation
expr = position.z > 3

# Translate and execute
stmt = eql_to_sql(expr, session)
rows = stmt.evaluate()  # → PositionDAO rows with z > 3

# More complex logic
expr2 = or_(position.z == 4, position.x == 2)
stmt2 = eql_to_sql(expr2, session)
rows2 = stmt.evaluate()

# Membership
expr3 = in_(position.x, [1, 7])
stmt3 = eql_to_sql(expr3, session)
rows3 = stmt.evaluate()
```

Notes on the EQL translator:
- Variable resolution uses `ormatic.dao.get_dao_class` to map EQL variables to DAO classes.
- Attribute comparisons on a single table are supported, including `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, 
logical `and`/`or`, and `not`.
- If a variable’s DAO class cannot be found, a specific EQL translation error is raised to help diagnose missing mappings.
- EQL translation is not complete, feel free to extend it
