"""calculator 工具测试：四则运算 + 非法输入拒绝（AST 白名单，绝不用 eval）。"""
import pytest

from app.tools.calculator import calculator, safe_calculate


def test_basic_arithmetic():
    assert safe_calculate("1+2*3") == "7"
    assert safe_calculate("(2+3)*4") == "20"
    assert safe_calculate("10/4") == "2.5"
    assert safe_calculate("10-2-3") == "5"


def test_unary_and_power():
    assert safe_calculate("-5+3") == "-2"
    assert safe_calculate("2**10") == "1024"
    assert safe_calculate("7%3") == "1"
    assert safe_calculate("7//2") == "3"


def test_integer_result_normalized():
    assert safe_calculate("4/2") == "2"  # 2.0 → "2"


def test_empty_expression_rejected():
    with pytest.raises(ValueError):
        safe_calculate("   ")


def test_import_rejected():
    with pytest.raises(Exception):
        safe_calculate("import os")


def test_dunder_call_rejected():
    with pytest.raises(Exception):
        safe_calculate("__import__('os').system('echo hi')")


def test_non_numeric_operand_rejected():
    with pytest.raises(Exception):
        safe_calculate("1+'a'")


def test_attribute_access_rejected():
    with pytest.raises(Exception):
        safe_calculate("(1).__class__")


def test_pow_exponent_capped():
    with pytest.raises(ValueError):
        safe_calculate("9**99999")


def test_division_by_zero_wrapped_by_tool():
    out = calculator.invoke({"expression": "1/0"})
    assert out.startswith("计算失败")


def test_tool_success_path():
    assert calculator.invoke({"expression": "1+1"}) == "2"
