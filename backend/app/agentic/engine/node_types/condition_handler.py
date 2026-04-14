from __future__ import annotations

import ast
from datetime import UTC, datetime
from typing import Any, Callable

from app.agentic.engine.node_types.base_handler import BaseNodeHandler
from app.agentic.models.agent_definition import ExecutionContext, NodeDefinition, NodeResult
from app.core.redis_client import redis_client


class UnsafeExpression(ValueError):
    pass


class _SafeExpressionEvaluator:
    def __init__(
        self,
        variables: dict[str, Any],
        functions: dict[str, Callable[..., Any]],
    ) -> None:
        self._variables = variables
        self._functions = functions

    def evaluate(self, expression: str) -> Any:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise UnsafeExpression("Invalid condition expression") from exc
        return self._eval(tree.body)

    def _eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id in {"True", "False", "None"}:
                return {"True": True, "False": False, "None": None}[node.id]
            if node.id not in self._variables:
                raise UnsafeExpression(f"Unknown variable '{node.id}'")
            return self._variables[node.id]

        if isinstance(node, ast.Attribute):
            base = self._eval(node.value)
            if node.attr.startswith("_"):
                raise UnsafeExpression("Private attribute access is not allowed")
            if isinstance(base, dict):
                return base.get(node.attr)
            return getattr(base, node.attr, None)

        if isinstance(node, ast.Subscript):
            container = self._eval(node.value)
            idx = self._eval(node.slice)
            if isinstance(container, dict):
                return container.get(idx)
            if isinstance(container, (list, tuple)) and isinstance(idx, int):
                if 0 <= idx < len(container):
                    return container[idx]
                return None
            return None

        if isinstance(node, ast.List):
            return [self._eval(item) for item in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(self._eval(item) for item in node.elts)

        if isinstance(node, ast.Dict):
            return {
                self._eval(key): self._eval(value)
                for key, value in zip(node.keys, node.values)
            }

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand)
            if isinstance(node.op, ast.Not):
                return not bool(operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise UnsafeExpression("Unsupported unary operator")

        if isinstance(node, ast.BoolOp):
            values = [bool(self._eval(value)) for value in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise UnsafeExpression("Unsupported boolean operator")

        if isinstance(node, ast.BinOp):
            left = self._eval(node.left)
            right = self._eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            raise UnsafeExpression("Unsupported binary operator")

        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for operator, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator)
                if isinstance(operator, ast.Eq):
                    ok = left == right
                elif isinstance(operator, ast.NotEq):
                    ok = left != right
                elif isinstance(operator, ast.Gt):
                    ok = left > right
                elif isinstance(operator, ast.GtE):
                    ok = left >= right
                elif isinstance(operator, ast.Lt):
                    ok = left < right
                elif isinstance(operator, ast.LtE):
                    ok = left <= right
                elif isinstance(operator, ast.In):
                    ok = left in right
                elif isinstance(operator, ast.NotIn):
                    ok = left not in right
                elif isinstance(operator, ast.Is):
                    ok = left is right
                elif isinstance(operator, ast.IsNot):
                    ok = left is not right
                else:
                    raise UnsafeExpression("Unsupported comparison operator")

                if not ok:
                    return False
                left = right
            return True

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise UnsafeExpression("Only allowlisted function calls are supported")

            fn_name = node.func.id
            fn = self._functions.get(fn_name)
            if fn is None:
                raise UnsafeExpression(f"Function '{fn_name}' is not allowlisted")
            if node.keywords:
                raise UnsafeExpression("Keyword arguments are not allowed")

            args = [self._eval(arg) for arg in node.args]
            return fn(*args)

        raise UnsafeExpression(f"Unsupported expression node: {type(node).__name__}")


def _rate_limit_ok_factory(exec_ctx: ExecutionContext) -> Callable[..., bool]:
    def _rate_limit_ok(rate_limit_key: str, user_alias: str, max_per_day: int = 3) -> bool:
        date_key = datetime.now(tz=UTC).strftime("%Y%m%d")
        redis_key = f"rate:{exec_ctx.ctx.tenant_id}:{rate_limit_key}:{user_alias}:{date_key}"
        try:
            current = redis_client.client.get(redis_key)
            current_count = int(current) if current is not None else 0
            return current_count < int(max_per_day)
        except Exception:
            # Fail-closed for rate-limit checks when backing store is unavailable.
            return False

    return _rate_limit_ok


def _redis_key_exists(cache_key: str) -> bool:
    try:
        return bool(redis_client.client.exists(cache_key))
    except Exception:
        return False


def safe_eval(expression: str, *, execution_context: ExecutionContext) -> bool:
    variables = {
        **execution_context.claim_sets,
        **execution_context.computed_values,
        "claim_set": {
            **execution_context.claim_sets,
            **execution_context.computed_values,
        },
        "ctx": execution_context.ctx,
        "intent": execution_context.intent,
    }

    functions: dict[str, Callable[..., Any]] = {
        "rate_limit_ok": _rate_limit_ok_factory(execution_context),
        "redis_key_exists": _redis_key_exists,
    }
    evaluator = _SafeExpressionEvaluator(variables=variables, functions=functions)
    value = evaluator.evaluate(expression)
    return bool(value)


class ConditionNodeHandler(BaseNodeHandler):
    async def execute(self, node: NodeDefinition, ctx: ExecutionContext) -> NodeResult:
        resolved_config = self.resolve_config(node, ctx)
        expression = resolved_config.get("expression")
        if expression is None:
            raise UnsafeExpression("Condition node requires 'expression' in config")

        if isinstance(expression, bool):
            outcome = expression
        elif not isinstance(expression, str):
            outcome = bool(expression)
        else:
            outcome = safe_eval(expression, execution_context=ctx)

        return NodeResult(
            output={"expression": expression, "result": outcome},
            condition_value=bool(outcome),
        )
