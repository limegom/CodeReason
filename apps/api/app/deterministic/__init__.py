"""Deterministic evidence collection and sandbox execution.

This package reports observations and does not assign scores.
"""

from .ast_analysis import ASTAnalysisReport, analyze_python_source
from .comparison import ComparisonMode, ComparisonResult, compare_outputs
from .docker_sandbox import DockerSandbox, SandboxExecutionResult, SandboxRequest
from .execution import ExecutionStatus, ResultAudience, TestExecutionResult
from .harness import (
    AssignmentExecutionConfig,
    ExecutionMode,
    FunctionArguments,
    TestCaseSpec,
)
from .types import (
    ASTFinding,
    EvidenceVisibility,
    ExecutionError,
    SourceCodeLocation,
    StaticFinding,
)

__all__ = [
    "ASTFinding",
    "ASTAnalysisReport",
    "AssignmentExecutionConfig",
    "ComparisonMode",
    "ComparisonResult",
    "DockerSandbox",
    "EvidenceVisibility",
    "ExecutionError",
    "ExecutionMode",
    "ExecutionStatus",
    "FunctionArguments",
    "ResultAudience",
    "SandboxExecutionResult",
    "SandboxRequest",
    "SourceCodeLocation",
    "StaticFinding",
    "TestCaseSpec",
    "TestExecutionResult",
    "analyze_python_source",
    "compare_outputs",
]
