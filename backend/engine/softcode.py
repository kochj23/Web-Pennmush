"""
Web-Pennmush Softcode Interpreter
Author: Jordan Koch (GitHub: kochj23)

Implements a MUSHcode interpreter for user-created content.
Supports common MUSH functions and attribute evaluation.
"""
from typing import Dict, Callable, Any, Optional
from backend.engine.objects import ObjectManager
from sqlalchemy.ext.asyncio import AsyncSession
import re
import random


class SoftcodeInterpreter:
    """
    Interprets and executes MUSHcode.

    MUSHcode syntax:
    - [function(args)]  - Function evaluation
    - %0-%9            - Substitutions (arguments)
    - #123             - Object reference
    - v(attr)          - Variable/attribute reference
    - get(obj/attr)    - Get attribute from object
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.obj_mgr = ObjectManager(session)
        self.functions: Dict[str, Callable] = {}
        self._register_functions()

    def _register_functions(self):
        """Register all softcode functions"""
        # String functions
        self.register_function("strlen", self.func_strlen)
        self.register_function("strcat", self.func_strcat)
        self.register_function("substr", self.func_substr)
        self.register_function("trim", self.func_trim)
        self.register_function("ucstr", self.func_ucstr)
        self.register_function("lcstr", self.func_lcstr)

        # Math functions
        self.register_function("add", self.func_add)
        self.register_function("sub", self.func_sub)
        self.register_function("mul", self.func_mul)
        self.register_function("div", self.func_div)
        self.register_function("mod", self.func_mod)
        self.register_function("rand", self.func_rand)

        # Logic functions
        self.register_function("eq", self.func_eq)
        self.register_function("neq", self.func_neq)
        self.register_function("gt", self.func_gt)
        self.register_function("gte", self.func_gte)
        self.register_function("lt", self.func_lt)
        self.register_function("lte", self.func_lte)
        self.register_function("and", self.func_and)
        self.register_function("or", self.func_or)
        self.register_function("not", self.func_not)

        # Conditional functions
        self.register_function("if", self.func_if)
        self.register_function("ifelse", self.func_ifelse)
        self.register_function("switch", self.func_switch)

        # Object functions
        self.register_function("name", self.func_name)
        self.register_function("num", self.func_num)
        self.register_function("loc", self.func_loc)
        self.register_function("owner", self.func_owner)
        self.register_function("get", self.func_get)
        self.register_function("v", self.func_v)

        # List functions
        self.register_function("words", self.func_words)
        self.register_function("first", self.func_first)
        self.register_function("rest", self.func_rest)
        self.register_function("last", self.func_last)

    def register_function(self, name: str, handler: Callable):
        """Register a softcode function"""
        self.functions[name.lower()] = handler

    async def eval(
        self,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        executor_id: Optional[int] = None
    ) -> str:
        """
        Evaluate MUSHcode and return the result.

        Args:
            code: The MUSHcode string to evaluate
            context: Context dictionary with variables (%0-%9, etc.)
            executor_id: Object ID of the executor (for v() lookups)

        Returns:
            The evaluated result as a string
        """
        if context is None:
            context = {}

        # Process substitutions (%0-%9, %#, etc.)
        code = self._process_substitutions(code, context, executor_id)

        # Process function calls [function(args)]
        code = await self._process_functions(code, context, executor_id)

        return code

    def _process_substitutions(self, code: str, context: Dict, executor_id: Optional[int]) -> str:
        """Process % substitutions"""
        # %0-%9: Arguments
        for i in range(10):
            if f"%{i}" in code:
                value = context.get(f"{i}", "")
                code = code.replace(f"%{i}", str(value))

        # %#: Executor ID
        if "%#" in code and executor_id is not None:
            code = code.replace("%#", str(executor_id))

        # %%: Literal %
        code = code.replace("%%", "%")

        return code

    async def _process_functions(self, code: str, context: Dict, executor_id: Optional[int]) -> str:
        """Process [function(args)] calls"""
        # Pattern: [function_name(args)]
        pattern = r'\[([a-zA-Z_][a-zA-Z0-9_]*)\(([^]]*)\)\]'

        while True:
            match = re.search(pattern, code)
            if not match:
                break

            func_name = match.group(1).lower()
            args_str = match.group(2)

            # Parse arguments (comma-separated)
            args = self._parse_args(args_str)

            # Execute function
            if func_name in self.functions:
                try:
                    result = await self.functions[func_name](args, context, executor_id)
                    code = code[:match.start()] + str(result) + code[match.end():]
                except Exception as e:
                    error_msg = f"#-1 ERROR: {str(e)}"
                    code = code[:match.start()] + error_msg + code[match.end():]
            else:
                error_msg = f"#-1 FUNCTION ({func_name}) NOT FOUND"
                code = code[:match.start()] + error_msg + code[match.end():]

        return code

    def _parse_args(self, args_str: str) -> list:
        """Parse comma-separated function arguments"""
        if not args_str.strip():
            return []

        # Simple comma split (TODO: Handle nested brackets)
        args = [arg.strip() for arg in args_str.split(",")]
        return args

    # ==================== STRING FUNCTIONS ====================

    async def func_strlen(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Return length of string"""
        if not args:
            return 0
        return len(args[0])

    async def func_strcat(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Concatenate strings"""
        return "".join(args)

    async def func_substr(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Extract substring"""
        if len(args) < 2:
            return ""
        string = args[0]
        start = int(args[1]) if args[1].isdigit() else 0
        length = int(args[2]) if len(args) > 2 and args[2].isdigit() else len(string)
        return string[start:start + length]

    async def func_trim(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Trim whitespace"""
        if not args:
            return ""
        return args[0].strip()

    async def func_ucstr(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Convert to uppercase"""
        if not args:
            return ""
        return args[0].upper()

    async def func_lcstr(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Convert to lowercase"""
        if not args:
            return ""
        return args[0].lower()

    # ==================== MATH FUNCTIONS ====================

    async def func_add(self, args: list, context: Dict, executor_id: Optional[int]) -> float:
        """Add numbers"""
        total = 0.0
        for arg in args:
            try:
                total += float(arg)
            except ValueError:
                pass
        return total

    async def func_sub(self, args: list, context: Dict, executor_id: Optional[int]) -> float:
        """Subtract numbers"""
        if len(args) < 2:
            return 0.0
        try:
            result = float(args[0])
            for arg in args[1:]:
                result -= float(arg)
            return result
        except ValueError:
            return 0.0

    async def func_mul(self, args: list, context: Dict, executor_id: Optional[int]) -> float:
        """Multiply numbers"""
        result = 1.0
        for arg in args:
            try:
                result *= float(arg)
            except ValueError:
                pass
        return result

    async def func_div(self, args: list, context: Dict, executor_id: Optional[int]) -> float:
        """Divide numbers"""
        if len(args) < 2:
            return 0.0
        try:
            result = float(args[0])
            for arg in args[1:]:
                divisor = float(arg)
                if divisor == 0:
                    return float('inf')
                result /= divisor
            return result
        except ValueError:
            return 0.0

    async def func_mod(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Modulo operation"""
        if len(args) < 2:
            return 0
        try:
            return int(args[0]) % int(args[1])
        except (ValueError, ZeroDivisionError):
            return 0

    async def func_rand(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Generate random number"""
        if not args:
            return random.randint(0, 100)
        try:
            max_val = int(args[0])
            min_val = int(args[1]) if len(args) > 1 else 0
            return random.randint(min_val, max_val)
        except ValueError:
            return 0

    # ==================== LOGIC FUNCTIONS ====================

    async def func_eq(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Equal comparison"""
        if len(args) < 2:
            return 0
        return 1 if args[0] == args[1] else 0

    async def func_neq(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Not equal comparison"""
        if len(args) < 2:
            return 0
        return 1 if args[0] != args[1] else 0

    async def func_gt(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Greater than"""
        if len(args) < 2:
            return 0
        try:
            return 1 if float(args[0]) > float(args[1]) else 0
        except ValueError:
            return 0

    async def func_gte(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Greater than or equal"""
        if len(args) < 2:
            return 0
        try:
            return 1 if float(args[0]) >= float(args[1]) else 0
        except ValueError:
            return 0

    async def func_lt(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Less than"""
        if len(args) < 2:
            return 0
        try:
            return 1 if float(args[0]) < float(args[1]) else 0
        except ValueError:
            return 0

    async def func_lte(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Less than or equal"""
        if len(args) < 2:
            return 0
        try:
            return 1 if float(args[0]) <= float(args[1]) else 0
        except ValueError:
            return 0

    async def func_and(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Logical AND"""
        return 1 if all(arg and arg != "0" for arg in args) else 0

    async def func_or(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Logical OR"""
        return 1 if any(arg and arg != "0" for arg in args) else 0

    async def func_not(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Logical NOT"""
        if not args:
            return 1
        return 0 if args[0] and args[0] != "0" else 1

    # ==================== CONDITIONAL FUNCTIONS ====================

    async def func_if(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """If conditional"""
        if len(args) < 2:
            return ""
        condition = args[0]
        true_val = args[1]
        return true_val if condition and condition != "0" else ""

    async def func_ifelse(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """If-else conditional"""
        if len(args) < 3:
            return ""
        condition = args[0]
        true_val = args[1]
        false_val = args[2]
        return true_val if condition and condition != "0" else false_val

    async def func_switch(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Switch statement"""
        if len(args) < 2:
            return ""
        value = args[0]
        # Format: switch(value, case1, result1, case2, result2, ..., default)
        for i in range(1, len(args) - 1, 2):
            if i + 1 < len(args) and args[i] == value:
                return args[i + 1]
        # Return default if exists
        return args[-1] if len(args) % 2 == 0 else ""

    # ==================== OBJECT FUNCTIONS ====================

    async def func_name(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get object name"""
        if not args:
            return ""
        try:
            obj_id = int(args[0].strip("#"))
            obj = await self.obj_mgr.get_object(obj_id)
            return obj.name if obj else "#-1 NOT FOUND"
        except ValueError:
            return "#-1 INVALID"

    async def func_num(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get object number"""
        if not args:
            return "#-1"
        obj = await self.obj_mgr.get_object_by_name(args[0])
        return f"#{obj.id}" if obj else "#-1"

    async def func_loc(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get object location"""
        if not args:
            return "#-1"
        try:
            obj_id = int(args[0].strip("#"))
            obj = await self.obj_mgr.get_object(obj_id)
            return f"#{obj.location_id}" if obj and obj.location_id else "#-1"
        except ValueError:
            return "#-1"

    async def func_owner(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get object owner"""
        if not args:
            return "#-1"
        try:
            obj_id = int(args[0].strip("#"))
            obj = await self.obj_mgr.get_object(obj_id)
            return f"#{obj.owner_id}" if obj and obj.owner_id else "#-1"
        except ValueError:
            return "#-1"

    async def func_get(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get attribute from object (obj/attr)"""
        if not args:
            return ""

        # Parse obj/attr
        if "/" not in args[0]:
            return "#-1 INVALID FORMAT"

        obj_ref, attr_name = args[0].split("/", 1)

        try:
            obj_id = int(obj_ref.strip("#"))
            attr = await self.obj_mgr.get_attribute(obj_id, attr_name)
            return attr.value if attr else ""
        except ValueError:
            return "#-1 INVALID"

    async def func_v(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get attribute from executor object"""
        if not args or executor_id is None:
            return ""

        attr_name = args[0]
        attr = await self.obj_mgr.get_attribute(executor_id, attr_name)
        return attr.value if attr else ""

    # ==================== LIST FUNCTIONS ====================

    async def func_words(self, args: list, context: Dict, executor_id: Optional[int]) -> int:
        """Count words in string"""
        if not args:
            return 0
        return len(args[0].split())

    async def func_first(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get first word"""
        if not args:
            return ""
        words = args[0].split()
        return words[0] if words else ""

    async def func_rest(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get all but first word"""
        if not args:
            return ""
        words = args[0].split()
        return " ".join(words[1:]) if len(words) > 1 else ""

    async def func_last(self, args: list, context: Dict, executor_id: Optional[int]) -> str:
        """Get last word"""
        if not args:
            return ""
        words = args[0].split()
        return words[-1] if words else ""
