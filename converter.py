import argparse
import sys
import math
from lark import Lark, Transformer, v_args, Tree
from lark.exceptions import LarkError
import xml.etree.ElementTree as ET
from xml.dom import minidom

GRAMMAR = """
start: item*

item: const
    | array
    | dict

const: "const" CNAME "=" value
value: number
     | array
     | dict
     | const_expr
     | CNAME

array: "(" [value ("," value)*] ")"
dict: "table" "(" "[" dict_entry ("," dict_entry)* "]" ")"
dict_entry: CNAME "=" value

const_expr: "|" expr "|"

expr: term
    | expr "+" term -> add
    | expr "-" term -> sub

term: factor
    | term "*" factor -> mul
    | term "/" factor -> div

factor: number
      | CNAME
      | "(" expr ")"
      | function

function: "len" "(" expr ")"
        | "abs" "(" expr ")"

number: SIGNED_NUMBER

CNAME: /[a-z][a-z0-9_]*/

%import common.SIGNED_NUMBER
%import common.WS
%ignore WS
%ignore /![^\\n]*/
%ignore /\\/#.*?#\\//
"""


class ConfigTransformer(Transformer):
    def __init__(self):
        self.constants = {}
        super().__init__()

    def _get_value(self, node):
        """Получает значение из узла или константы"""
        if isinstance(node, Tree):
            # Трансформируем дерево
            return self._transform_tree(node)
        elif isinstance(node, str):
            # Если это строка, проверяем, не константа ли это
            if node in self.constants:
                return self.constants[node]
            return node
        else:
            # Число или другое значение
            return node

    def _transform_tree(self, tree):
        """Трансформирует дерево Lark в значение"""
        if tree.data == 'value':
            return self.value(tree.children)
        elif tree.data == 'const_expr':
            return self.const_expr(tree.children)
        elif tree.data == 'add':
            return self._eval_binary_op(tree.children, lambda a, b: a + b)
        elif tree.data == 'sub':
            return self._eval_binary_op(tree.children, lambda a, b: a - b)
        elif tree.data == 'mul':
            return self._eval_binary_op(tree.children, lambda a, b: a * b)
        elif tree.data == 'div':
            return self._eval_binary_op(tree.children, lambda a, b: a / b if b != 0 else self._zero_division_error())
        elif tree.data == 'function':
            return self._eval_function(tree)
        elif tree.data in ('expr', 'term', 'factor'):
            # Для внутренних узлов рекурсивно трансформируем
            return self._get_value(tree.children[0])
        else:
            # Для других узлов вызываем соответствующий метод
            try:
                method = getattr(self, tree.data)
                return method(tree.children)
            except AttributeError:
                return tree

    def _eval_binary_op(self, children, op_func):
        """Вычисляет бинарную операцию"""
        left = self._get_value(children[0])
        right = self._get_value(children[1])

        if not (isinstance(left, (int, float)) and isinstance(right, (int, float))):
            raise TypeError(f"Operation requires numbers, got {type(left)} and {type(right)}")

        return op_func(left, right)

    def _eval_function(self, tree):
        """Вычисляет функцию"""
        # Получаем имя функции и аргумент из дерева
        func_name = tree.children[0]  # 'len' или 'abs'

        # Второй элемент - это дерево с выражением
        arg_tree = tree.children[1]
        arg = self._get_value(arg_tree)

        if func_name == "len":
            if isinstance(arg, list):
                return len(arg)
            raise TypeError(f"len() requires array, got {type(arg)}")
        elif func_name == "abs":
            if isinstance(arg, (int, float)):
                return abs(arg)
            raise TypeError(f"abs() requires number, got {type(arg)}")
        raise ValueError(f"Unknown function: {func_name}")

    def _zero_division_error(self):
        """Вызывает ошибку деления на ноль"""
        raise ZeroDivisionError("Division by zero")

    def CNAME(self, token):
        return token.value

    def number(self, n):
        val = float(n[0].value)
        return int(val) if val.is_integer() else val

    def array(self, items):
        return [self._get_value(item) for item in items]

    def dict(self, items):
        return {k: self._get_value(v) for k, v in items}

    def dict_entry(self, items):
        key = str(items[0])
        value = items[1]
        return (key, value)

    def const_expr(self, children):
        return self._get_value(children[0])

    def const(self, children):
        name = str(children[0])
        raw_value = children[1]

        # Вычисляем значение константы
        value = self._get_value(raw_value)
        self.constants[name] = value
        return ('const', name, value)

    def value(self, children):
        return self._get_value(children[0])

    def item(self, children):
        return children[0]

    def start(self, items):
        return items


def value_to_xml(value, parent):
    if isinstance(value, (int, float)):
        elem = ET.SubElement(parent, "number")
        elem.text = str(value)
        elem.set("type", "integer" if isinstance(value, int) else "float")
    elif isinstance(value, list):
        elem = ET.SubElement(parent, "array")
        for item in value:
            value_to_xml(item, elem)
    elif isinstance(value, dict):
        elem = ET.SubElement(parent, "dict")
        for k, v in value.items():
            entry = ET.SubElement(elem, "entry")
            entry.set("key", str(k))
            value_to_xml(v, entry)
    elif isinstance(value, tuple) and value[0] == 'const':
        elem = ET.SubElement(parent, "const")
        elem.set("name", value[1])
        value_to_xml(value[2], elem)
    elif isinstance(value, str):
        elem = ET.SubElement(parent, "string")
        elem.text = value
    else:
        elem = ET.SubElement(parent, "value")
        elem.text = str(value)


def prettify_xml(elem):
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def main():
    parser = argparse.ArgumentParser(description="Configuration language to XML converter")
    parser.add_argument("-i", "--input", required=True, help="Input file path")
    parser.add_argument("-o", "--output", required=True, help="Output XML file path")
    args = parser.parse_args()

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: Input file '{args.input}' not found")
        sys.exit(1)

    try:
        parser = Lark(GRAMMAR, parser='lalr', transformer=ConfigTransformer())
        result = parser.parse(source)

        root = ET.Element("config")
        for item in result:
            value_to_xml(item, root)

        xml_str = prettify_xml(root)

        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(xml_str)

    except LarkError as e:
        print(f"Syntax error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Semantic error: {e}")
        sys.exit(1)
    except ZeroDivisionError:
        print(f"Runtime error: Division by zero")
        sys.exit(1)
    except TypeError as e:
        print(f"Type error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()