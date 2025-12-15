import unittest
from lark import Lark
from converter import ConfigTransformer, GRAMMAR


class TestBasic(unittest.TestCase):
    def test_simple(self):
        data = "const x = 5"
        parser = Lark(GRAMMAR, parser='lalr', transformer=ConfigTransformer())
        result = parser.parse(data)
        print(f"Test 1 result: {result}")
        self.assertEqual(result[0][2], 5)

    def test_simple_expression(self):
        data = "const x = |10 / 2|"
        parser = Lark(GRAMMAR, parser='lalr', transformer=ConfigTransformer())
        result = parser.parse(data)
        print(f"Test 2 result: {result}")
        self.assertEqual(result[0][2], 5)

    def test_const_reference(self):
        data = "const a = 10\nconst b = |a * 2|"
        parser = Lark(GRAMMAR, parser='lalr', transformer=ConfigTransformer())
        result = parser.parse(data)
        print(f"Test 3 result: {result}")
        self.assertEqual(result[1][2], 20)


if __name__ == '__main__':
    unittest.main()