"""
sandbox.py — validation and guarded loading of submitted bot code.

Submitted bots are untrusted. Defense is layered:
  1. AST validation: only allowlisted imports, no exec/eval/open/dunder access.
  2. Guarded execution: restricted builtins + an allowlisting __import__.
  3. Per-move wall-clock timer (SIGALRM) enforcing the 5s house rule.
  4. Outside this module: the Lambda's IAM role can only touch the camel-up
     S3 prefixes, its env holds no secrets, and the 15-min invocation
     timeout backstops anything that ignores the alarm.
"""

import ast
import builtins as _builtins
import signal

# Stdlib-only compute is the norm for bots (see README / HANDOFF).
ALLOWED_IMPORTS = {
    "math", "random", "itertools", "functools", "collections", "heapq",
    "bisect", "statistics", "operator", "copy", "time", "hashlib", "uuid",
    "dataclasses", "enum", "typing", "string", "array", "decimal", "fractions",
    # Game modules bots are documented to use.
    "camelup", "playerinterface",
}

BANNED_NAMES = {
    "exec", "eval", "compile", "open", "input", "breakpoint", "__import__",
    "globals", "locals", "vars", "memoryview", "exit", "quit", "help",
}

SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bin", "bool", "bytearray", "bytes", "callable",
    "chr", "classmethod", "complex", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "getattr", "hasattr", "hash", "hex",
    "id", "int", "isinstance", "issubclass", "iter", "len", "list", "map",
    "max", "min", "next", "object", "oct", "ord", "pow", "print", "property",
    "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
    "staticmethod", "str", "sum", "super", "tuple", "type", "zip",
    # Exceptions bots legitimately raise/catch.
    "ArithmeticError", "AssertionError", "AttributeError", "BaseException",
    "Exception", "GeneratorExit", "IndexError", "KeyError", "KeyboardInterrupt",
    "LookupError", "NameError", "NotImplementedError", "OverflowError",
    "RecursionError", "RuntimeError", "StopIteration", "TypeError",
    "ValueError", "ZeroDivisionError",
    "True", "False", "None", "NotImplemented", "Ellipsis",
]


class BotValidationError(Exception):
    """Submitted code failed static validation. str() is the human reason."""


class MoveTimeout(Exception):
    """A bot exceeded the per-move time limit."""


def validate_bot_source(code, expected_class=None):
    """
    Statically validate submitted bot source. Returns the bot class name.
    Raises BotValidationError with a submitter-friendly reason.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise BotValidationError(f"Python syntax error on line {e.lineno}: {e.msg}")

    move_classes = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    raise BotValidationError(
                        f"import of '{alias.name}' is not allowed "
                        f"(allowed: {', '.join(sorted(ALLOWED_IMPORTS))})"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level != 0 or root not in ALLOWED_IMPORTS:
                raise BotValidationError(
                    f"import from '{node.module or '.'}' is not allowed "
                    f"(allowed: {', '.join(sorted(ALLOWED_IMPORTS))})"
                )
        elif isinstance(node, ast.Name):
            if node.id in BANNED_NAMES:
                raise BotValidationError(f"use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute):
            # Blocks sandbox escapes via __globals__ / __subclasses__ / etc.
            # Name-mangled privates (self.__cache) don't end in '__' so pass.
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise BotValidationError(
                    f"dunder attribute access ('.{node.attr}') is not allowed"
                )
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "move":
                    move_classes.append(node.name)

    if not move_classes:
        raise BotValidationError(
            "no bot class found: the file must define a class with a "
            "move(player, gamestate) method"
        )

    if expected_class and expected_class in move_classes:
        return expected_class
    return move_classes[-1]


def load_bot_class(code, class_name):
    """
    Exec validated source in a restricted namespace and return the bot class.
    Raises BotValidationError if execution fails or the class is missing.
    """
    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0 or name.split(".")[0] not in ALLOWED_IMPORTS:
            raise ImportError(f"import of '{name}' is not allowed")
        return _builtins.__import__(name, globals, locals, fromlist, level)

    safe_builtins = {n: getattr(_builtins, n) for n in SAFE_BUILTIN_NAMES if hasattr(_builtins, n)}
    safe_builtins["__import__"] = guarded_import
    safe_builtins["__build_class__"] = _builtins.__build_class__

    namespace = {"__builtins__": safe_builtins, "__name__": "submitted_bot"}

    try:
        exec(compile(code, "<submitted_bot>", "exec"), namespace)  # noqa: S102 — sandboxed on purpose
    except Exception as e:
        raise BotValidationError(f"bot code failed to execute: {type(e).__name__}: {e}")

    cls = namespace.get(class_name)
    if cls is None or not isinstance(cls, type):
        raise BotValidationError(f"class '{class_name}' not found after executing the file")
    return cls


class TimedBot:
    """
    Wraps a bot class with a per-move SIGALRM wall-clock limit. run_game
    treats the raised MoveTimeout like any bot crash (falls back to a roll);
    the handler checks .timeouts afterwards to disqualify the bot.
    """

    def __init__(self, cls, limit_s=5.0):
        self._cls = cls
        self.limit_s = limit_s
        self.timeouts = 0

    def move(self, player, g):
        def _on_alarm(signum, frame):
            raise MoveTimeout()

        previous = signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, self.limit_s)
        try:
            return self._cls.move(player, g)
        except MoveTimeout:
            self.timeouts += 1
            raise
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
