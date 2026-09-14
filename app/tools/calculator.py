"""安全计算器：基于 AST 白名单解析四则运算，绝不使用 eval。"""
import ast
import operator

from langchain_core.tools import tool

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_POW_EXPONENT = 1000


def _evaluate(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW_EXPONENT:
            raise ValueError(f"指数过大（上限 {_MAX_POW_EXPONENT}）")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_evaluate(node.operand))
    raise ValueError("仅支持数字与 + - * / % ** ( ) 组成的四则运算")


def safe_calculate(expression: str) -> str:
    """纯函数版计算入口，便于测试与复用；非法输入抛异常。"""
    expression = (expression or "").strip()
    if not expression:
        raise ValueError("表达式为空")
    tree = ast.parse(expression, mode="eval")
    result = _evaluate(tree)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)


@tool
def calculator(expression: str) -> str:
    """计算数学表达式（四则运算 + - * / % ** 与括号）。输入必须是纯表达式字符串，例如 "1+2*3"。"""
    try:
        return safe_calculate(expression)
    except Exception as exc:  # 工具层兜底：把异常转成文本反馈给 LLM
        return f"计算失败：{exc}"
