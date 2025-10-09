from pathlib import Path


from krrood.class_diagrams.class_diagram import ClassDiagram
from krrood.class_diagrams.utils import classes_of_module


def test_class_diagram_visualization():
    classes = classes_of_module(datasets)
    diagram = ClassDiagram(classes)

    output_file = "test_class_diagram.pdf"
    diagram.visualize(filename=output_file, title="Test Class Diagram")

    # Verify the output file was created
    assert Path(
        output_file
    ).exists(), f"Visualization file {output_file} was not created"

    # Clean up
    # Path(output_file).unlink()
