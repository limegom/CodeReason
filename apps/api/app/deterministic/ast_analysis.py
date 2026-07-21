"""Conservative Python AST and static evidence collection."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable, Sequence

from .types import (
    ASTFinding,
    ExecutionError,
    FindingSeverity,
    SourceCodeLocation,
    StaticFinding,
)


@dataclass(frozen=True, slots=True)
class ASTAnalysisReport:
    ast_findings: tuple[ASTFinding, ...]
    static_findings: tuple[StaticFinding, ...]
    syntax_error: ExecutionError | None = None

    def feature_summary(self) -> dict[str, bool | None]:
        """Return stable features suitable for a consistency fingerprint."""

        selected = {
            "syntax_valid",
            "expected_function_exists",
            "signature_matches",
            "return_present",
            "loop_present",
            "conditional_present",
            "list_comprehension_present",
            "recursion_present",
        }
        return {
            finding.rule: finding.passed
            for finding in self.ast_findings
            if finding.rule in selected
        }


def _location(filename: str, node: ast.AST) -> SourceCodeLocation:
    return SourceCodeLocation(
        file=filename,
        line_start=max(1, int(getattr(node, "lineno", 1))),
        line_end=max(1, int(getattr(node, "end_lineno", getattr(node, "lineno", 1)))),
        column_start=getattr(node, "col_offset", None),
        column_end=getattr(node, "end_col_offset", None),
    )


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = [node.func.attr]
        value = node.func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
            return ".".join(reversed(parts))
    return None


def _literal_leaf_count(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant):
        return 1
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        counts = [_literal_leaf_count(item) for item in node.elts]
    elif isinstance(node, ast.Dict):
        counts = [_literal_leaf_count(item) for item in node.values]
    else:
        return None
    if any(count is None for count in counts):
        return None
    return sum(int(count) for count in counts)


class _EvidenceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        self.loops: list[ast.For | ast.AsyncFor | ast.While] = []
        self.conditionals: list[ast.If | ast.IfExp | ast.Match] = []
        self.comprehensions: list[ast.ListComp] = []
        self.returns: list[ast.Return] = []
        self.recursive_calls: list[ast.Call] = []
        self.imports: list[tuple[str, ast.AST]] = []
        self.global_statements: list[ast.Global] = []
        self.module_assignments: list[ast.Assign | ast.AnnAssign] = []
        self.close_calls: list[ast.Call] = []
        self.dangerous_calls: list[tuple[str, ast.Call]] = []
        self.literal_candidates: list[ast.AST] = []
        self._function_stack: list[str] = []
        self._scope_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node)
        self._function_stack.append(node.name)
        self._scope_depth += 1
        self.generic_visit(node)
        self._scope_depth -= 1
        self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.functions.append(node)
        self._function_stack.append(node.name)
        self._scope_depth += 1
        self.generic_visit(node)
        self._scope_depth -= 1
        self._function_stack.pop()

    def visit_For(self, node: ast.For) -> None:
        self.loops.append(node)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.loops.append(node)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.loops.append(node)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.conditionals.append(node)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.conditionals.append(node)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.conditionals.append(node)
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.comprehensions.append(node)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.global_statements.append(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._scope_depth == 0:
            self.module_assignments.append(node)
        leaf_count = _literal_leaf_count(node.value)
        if leaf_count is not None and leaf_count >= 4:
            self.literal_candidates.append(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._scope_depth == 0:
            self.module_assignments.append(node)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        self.returns.append(node)
        leaf_count = _literal_leaf_count(node.value)
        if leaf_count is not None and leaf_count >= 4 and node.value is not None:
            self.literal_candidates.append(node.value)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append((alias.name, node))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self.imports.append((f"{module}.{alias.name}".strip("."), node))

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name and self._function_stack and name == self._function_stack[-1]:
            self.recursive_calls.append(node)
        if name and (name == "close" or name.endswith(".close")):
            self.close_calls.append(node)
        dangerous_names = {"eval", "exec", "compile", "__import__", "os.system"}
        if name in dangerous_names or (name and name.startswith("subprocess.")):
            self.dangerous_calls.append((name, node))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and (
            re.search(r"\.(?:txt|csv|json|db|sqlite|key|pem)$", node.value, re.I)
            or "/" in node.value
            or "\\" in node.value
        ):
            self.literal_candidates.append(node)


def _boolean_finding(
    rule: str,
    nodes: Sequence[ast.AST],
    filename: str,
    present_message: str,
    absent_message: str,
) -> ASTFinding:
    return ASTFinding(
        rule=rule,
        passed=bool(nodes),
        message=present_message if nodes else absent_message,
        location=_location(filename, nodes[0]) if nodes else None,
        details={"occurrences": len(nodes)},
    )


def _parameter_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    args = function.args
    return [
        *(argument.arg for argument in args.posonlyargs),
        *(argument.arg for argument in args.args),
        *(argument.arg for argument in args.kwonlyargs),
    ]


def analyze_python_source(
    source_code: str,
    *,
    filename: str = "submission.py",
    expected_function: str | None = None,
    expected_parameters: Iterable[str] | None = None,
) -> ASTAnalysisReport:
    """Collect observable syntax/shape findings without inferring intent."""

    if (
        "/" in filename
        or "\\" in filename
        or PurePath(filename).name != filename
        or not filename.endswith(".py")
    ):
        raise ValueError("filename must be a .py basename")
    try:
        tree = ast.parse(source_code, filename=filename)
    except SyntaxError as exc:
        location = SourceCodeLocation(
            file=filename,
            line_start=max(1, exc.lineno or 1),
            line_end=max(1, exc.end_lineno or exc.lineno or 1),
            column_start=max(0, (exc.offset or 1) - 1),
            column_end=max(0, (exc.end_offset or exc.offset or 1) - 1),
        )
        error = ExecutionError(
            category="SYNTAX_ERROR",
            exception_type="SyntaxError",
            message=exc.msg,
            location=location,
        )
        return ASTAnalysisReport(
            ast_findings=(
                ASTFinding(
                    rule="syntax_valid",
                    passed=False,
                    message="Python parsing reported a syntax error.",
                    location=location,
                ),
            ),
            static_findings=(),
            syntax_error=error,
        )

    visitor = _EvidenceVisitor()
    visitor.visit(tree)
    findings: list[ASTFinding] = [
        ASTFinding(
            rule="syntax_valid",
            passed=True,
            message="Python parsing completed without a syntax error.",
        )
    ]

    target_function = None
    if expected_function:
        target_function = next(
            (function for function in visitor.functions if function.name == expected_function),
            None,
        )
        findings.append(
            ASTFinding(
                rule="expected_function_exists",
                passed=target_function is not None,
                message=(
                    f"Function {expected_function!r} is defined."
                    if target_function
                    else f"No function definition named {expected_function!r} was found."
                ),
                location=_location(filename, target_function) if target_function else None,
                details={"expected_function": expected_function},
            )
        )
        if target_function is not None:
            observed_parameters = _parameter_names(target_function)
            findings.append(
                ASTFinding(
                    rule="function_signature_observed",
                    passed=None,
                    message=(
                        f"Function {expected_function!r} defines "
                        f"{len(observed_parameters)} named parameter(s)."
                    ),
                    location=_location(filename, target_function),
                    details={
                        "parameter_count": len(observed_parameters),
                        "parameter_names": observed_parameters,
                        "vararg": (
                            target_function.args.vararg.arg
                            if target_function.args.vararg
                            else None
                        ),
                        "kwarg": (
                            target_function.args.kwarg.arg
                            if target_function.args.kwarg
                            else None
                        ),
                    },
                )
            )
        if expected_parameters is not None:
            expected = list(expected_parameters)
            actual = _parameter_names(target_function) if target_function else []
            matches = target_function is not None and actual == expected
            findings.append(
                ASTFinding(
                    rule="signature_matches",
                    passed=matches,
                    message=(
                        "The defined parameter names match the assignment signature."
                        if matches
                        else "The observed parameter names do not match the assignment signature."
                    ),
                    location=_location(filename, target_function) if target_function else None,
                    details={"expected": expected, "observed": actual},
                )
            )

    if expected_function:
        target_nodes = list(ast.walk(target_function)) if target_function else []
    else:
        target_nodes = list(ast.walk(tree))
    target_returns = [node for node in target_nodes if isinstance(node, ast.Return)]
    target_loops = [
        node for node in target_nodes if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
    ]
    target_conditionals = [
        node for node in target_nodes if isinstance(node, (ast.If, ast.IfExp, ast.Match))
    ]
    target_comprehensions = [node for node in target_nodes if isinstance(node, ast.ListComp)]
    target_close_calls = [
        node
        for node in target_nodes
        if isinstance(node, ast.Call)
        and (name := _call_name(node)) is not None
        and (name == "close" or name.endswith(".close"))
    ]
    target_recursion = [
        node
        for node in target_nodes
        if isinstance(node, ast.Call)
        and expected_function
        and _call_name(node) == expected_function
    ]
    findings.extend(
        [
            _boolean_finding(
                "return_present",
                target_returns,
                filename,
                "A return statement appears in the analyzed function scope.",
                "No return statement appears in the analyzed function scope.",
            ),
            _boolean_finding(
                "loop_present",
                target_loops,
                filename,
                "A loop node appears in the analyzed function scope.",
                "No loop node appears in the analyzed function scope.",
            ),
            _boolean_finding(
                "conditional_present",
                target_conditionals,
                filename,
                "A conditional node appears in the analyzed function scope.",
                "No conditional node appears in the analyzed function scope.",
            ),
            _boolean_finding(
                "list_comprehension_present",
                target_comprehensions,
                filename,
                "A list comprehension appears in the analyzed function scope.",
                "No list comprehension appears in the analyzed function scope.",
            ),
            _boolean_finding(
                "recursion_present",
                target_recursion,
                filename,
                "A direct call to the analyzed function appears in its body.",
                "No direct recursive call appears in the analyzed function body.",
            ),
            _boolean_finding(
                "close_call_present",
                target_close_calls,
                filename,
                "A close() call appears in the analyzed function scope.",
                "No close() call appears in the analyzed function scope.",
            ),
        ]
    )

    for module, node in visitor.imports:
        findings.append(
            ASTFinding(
                rule="import_observed",
                passed=None,
                message=f"Import {module!r} appears in the source.",
                location=_location(filename, node),
                details={"module": module},
            )
        )
    for node in visitor.global_statements:
        findings.append(
            ASTFinding(
                rule="global_statement_observed",
                passed=None,
                message="A global statement appears in the source.",
                location=_location(filename, node),
                details={"names": list(node.names)},
            )
        )
    for node in visitor.close_calls:
        findings.append(
            ASTFinding(
                rule="close_call_observed",
                passed=None,
                message="A close() call appears in the source.",
                location=_location(filename, node),
            )
        )

    static_findings: list[StaticFinding] = []
    for call_name, node in visitor.dangerous_calls:
        static_findings.append(
            StaticFinding(
                rule="restricted_api_reference",
                message=f"A call to restricted API {call_name!r} appears in the source.",
                severity=FindingSeverity.SECURITY,
                location=_location(filename, node),
                details={"call": call_name},
            )
        )
    for node in visitor.literal_candidates:
        static_findings.append(
            StaticFinding(
                rule="hardcoded_literal_candidate",
                message=(
                    "A literal path or sizeable literal collection appears here; "
                    "this is a review candidate and does not establish intent."
                ),
                severity=FindingSeverity.WARNING,
                location=_location(filename, node),
            )
        )
    for node in visitor.module_assignments:
        static_findings.append(
            StaticFinding(
                rule="module_level_assignment",
                message="An assignment appears at module scope.",
                severity=FindingSeverity.INFO,
                location=_location(filename, node),
            )
        )

    return ASTAnalysisReport(
        ast_findings=tuple(findings),
        static_findings=tuple(static_findings),
    )
