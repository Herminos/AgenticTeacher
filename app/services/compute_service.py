import ast
import asyncio
import multiprocessing as mp
from typing import Any


ALLOWED_CALLS = {"integrate", "diff", "solve", "simplify", "limit", "factor", "expand"}
ALLOWED_NODES = (ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Tuple, ast.List, ast.Eq, ast.Compare)


def _validate_tree(tree: ast.AST) -> None:
    nodes = list(ast.walk(tree))
    if len(nodes) > 80:
        raise ValueError("expression is too complex")
    for node in nodes:
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_CALLS:
                raise ValueError("function is not allowed")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str)):
            raise ValueError("constant type is not allowed")


def _eval_node(node: ast.AST, symbols: dict[str, Any], sp: Any) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, symbols, sp)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in symbols:
            if len(node.id) > 3 or not node.id.isalpha():
                raise ValueError("symbol is not allowed")
            symbols[node.id] = sp.Symbol(node.id)
        return symbols[node.id]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(item, symbols, sp) for item in node.elts)
    if isinstance(node, ast.List):
        return [_eval_node(item, symbols, sp) for item in node.elts]
    if isinstance(node, ast.UnaryOp):
        value = _eval_node(node.operand, symbols, sp)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _eval_node(node.left, symbols, sp), _eval_node(node.right, symbols, sp)
        operations = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right, ast.Mult: lambda: left * right, ast.Div: lambda: left / right, ast.Pow: lambda: left**right}
        operation = next((fn for cls, fn in operations.items() if isinstance(node.op, cls)), None)
        if operation is None:
            raise ValueError("operator is not allowed")
        return operation()
    if isinstance(node, ast.Compare):
        left, right = _eval_node(node.left, symbols, sp), _eval_node(node.comparators[0], symbols, sp)
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            raise ValueError("only equality is allowed")
        return sp.Eq(left, right)
    if isinstance(node, ast.Call):
        name = node.func.id
        args = [_eval_node(arg, symbols, sp) for arg in node.args]
        functions = {
            "integrate": sp.integrate,
            "diff": sp.diff,
            "solve": sp.solve,
            "simplify": sp.simplify,
            "limit": sp.limit,
            "factor": sp.factor,
            "expand": sp.expand,
        }
        return functions[name](*args)
    raise ValueError("unsupported expression")


def _compute_sync(expression: str) -> str:
    import sympy as sp

    tree = ast.parse(expression, mode="eval")
    _validate_tree(tree)
    result = _eval_node(tree, {}, sp)
    return str(result)


def _worker(expression: str, conn: Any) -> None:
    try:
        conn.send((True, _compute_sync(expression)))
    except Exception as exc:  # do not send traceback to clients
        conn.send((False, str(exc)))
    finally:
        conn.close()


def _run_process(expression: str, timeout_seconds: float) -> tuple[bool, str]:
    parent, child = mp.Pipe(False)
    process = mp.Process(target=_worker, args=(expression, child), daemon=True)
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(0.2)
        return False, "computation timed out"
    if parent.poll():
        return parent.recv()
    return False, "computation failed"


class ComputeService:
    async def compute(self, expression: str, timeout_ms: int) -> tuple[str, list[str], bool]:
        loop = asyncio.get_running_loop()
        ok, value = await loop.run_in_executor(None, _run_process, expression, timeout_ms / 1000)
        if not ok:
            raise ValueError(value)
        return value, [], True
