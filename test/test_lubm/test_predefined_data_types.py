from __future__ import annotations

from krrood.experiments.owl_to_python import OwlToPythonConverter


def test_age_name_and_tenured_types():
    overrides = {
        "Person": {
            "age": "int",
            "name": "str",
        },
        "Professor": {
            "tenured": "bool",
        },
    }
    conv = OwlToPythonConverter(predefined_data_types=overrides)
    conv.load_ontology("../resources/lubm.owl")
    code = conv.generate_python_code_external()

    # Check that the generated code includes the correct type hints
    assert "class Person" in code
    assert "age: Optional[int] = field(kw_only=True, default=None)" in code
    assert "name: Optional[str] = field(kw_only=True, default=None)" in code

    assert "class Professor" in code
    assert "tenured: Optional[bool] = field(kw_only=True, default=None)" in code
