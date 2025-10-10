import unittest
from dataclasses import fields

from dataset.cyclic_imports import PoseAnnotation
from krrood.ormatic.field_info import FieldInfo


class UnfinishedTypeTestCase(unittest.TestCase):

    def test_unfinished_type_field_info(self):
        f = [f for f in fields(PoseAnnotation) if f.name == "pose"][0]
        fi = FieldInfo(PoseAnnotation, f)


if __name__ == "__main__":
    unittest.main()
