# Author: Boyan Ding
import copy

from intbase import InterpreterBase, ErrorType
from brewparse import parse_program

class BrewinValue:
    """
    Values in Brewin V4, representing both lazy eval "need" or
    evaluated values

    The need is constructed using the need field.
    Its value is constructed from AST, where all operands are replaced with other
    BrewinValue by looking up in the scopes, which is different from a lot of other
    impls that stores original AST and a special env. The approaches are isomorphic,
    though.

    Special case: name error created during lazy evaluation is represented with
    evaled = False and need = None (real nils will always have evaled = True)

    """
    def __init__(self, evaled, value_or_need):
        self.evaled = evaled
        if evaled:
            self.value = value_or_need
            self.need = None
        else:
            self.value = None
            self.need = value_or_need

    @classmethod
    def get_nil(cls):
        return BrewinValue(True, None)

    @classmethod
    def get_poison(cls):
        return BrewinValue(False, None)

    def is_nil(self):
        return self.evaled and self.value is None

    def is_poison(self):
        return not self.evaled and self.need is None

    # Type checking (no coercion allowed) returns None on error
    @classmethod
    def ensure_type(cls, val, rtype):
        match rtype:
            case 'int':
                if type(val) == int:
                    return val
            case 'bool':
                if type(val) == bool:
                    return val
            case 'string':
                if type(val) == str:
                    return val
        # Those that have not returned are errors, report error at caller
        return None

class BrewinException:
    """
    Exception handling

    * First, we cannot use Python's exception handling to handle Brewin exception
      because it will mess up scoping
    * Second, a raise is treated as a special form of return, where the returned
      value is of type BrewinException, special cases
      * (1) any statement using eager eval (?) need to check if result is exception
           - Function arguments
           - Expressions
           in case an exception is obtained, directly return that exception
      * If a try block gets exception, see if any catch matches the exception
    """
    def __init__(self, msg):
        self.msg = msg

class BrewinPrintException(Exception):
    def __init__(self, exc):
        self.exc = exc

class BrewinProgram:
    # Stores return type and node
    class BrewinFunction:
        def __init__(self, funcnode):
            self.ast = funcnode

        def name(self):
            return self.ast.get('name')

        def arglen(self):
            return len(self.ast.get('args'))
        
        def statements(self):
            return self.ast.get('statements')

    # Initialization
    def __init__(self, program: str, interp: InterpreterBase):
        self.prog = program
        self.ast = parse_program(program)

        # print(self.ast)
        self.__build_func_dict(interp)

    def __build_func_dict(self, interp: InterpreterBase):
        self.func_dict = {}
        for func in self.ast.get('functions'):
            bf = self.BrewinFunction(func)
            self.func_dict[(bf.name(), bf.arglen())] = bf

    def get_function(self, name, arglen):
        return self.func_dict.get((name, arglen))

class ScopeEnv:
    def __init__(self, interp):
        self.func_scopes = []
        self.interp = interp

    def reset(self):
        self.func_scopes = []

    def enter_func(self):
        # Add a default block inside a function (for arguments)
        self.func_scopes.append([{}])

    def exit_func(self):
        self.func_scopes.pop()

    def enter_block(self):
        self.func_scopes[-1].append({})

    def exit_block(self):
        self.func_scopes[-1].pop()

    def define_var(self, name):
        if name in self.func_scopes[-1][-1]:
            self.interp.error(ErrorType.NAME_ERROR, f"Redefining variable '{name}'")
        else:
            self.func_scopes[-1][-1][name] = BrewinValue.get_nil()

    def assign(self, name, value):
        self.__assign_get(name, value)

    def get_value(self, name):
        return self.__assign_get(name, None)

    def __assign_get(self, name, value_or_get):
        # Implements both variable assignment and read, depending on value_or_get
        # Remnants of project 3 logic (yeah, this is adapted from my p3 code)

        # Find the variable in scope and perform op
        for scope in reversed(self.func_scopes[-1]):
            if name in scope:
                if value_or_get is not None:
                    scope[name] = value_or_get
                    return
                else:
                    return scope[name]

        # Variable not in scope
        # throw error for assignment (because the value will never be used)
        # poison for read (delay error)
        if value_or_get is None:
            return BrewinValue.get_poison()
        self.interp.error(ErrorType.NAME_ERROR, f"Variable {name} not in scope for assignment")

class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.env = ScopeEnv(self)

    # Initialization Routines
    def run(self, program):
        self.prog = BrewinProgram(program, self)

        self.env.reset()

        # Result is discarded for main function
        ret_val = self.__exec_func('main', [])
        if isinstance(ret_val, BrewinException):
            self.error(ErrorType.FAULT_ERROR, f"Unhandled exception {ret_val.msg}")

    # Execute a function, returns need for result without eager eval, or an exception
    def __exec_func(self, func_name, args):
        if func_name == 'inputi':
            return self.__lib_inputi(args)
        elif func_name == 'inputs':
            return self.__lib_inputs(args)
        elif func_name == 'print':
            # print returns nil
            return self.__lib_print(args)
        else:
            bf = self.prog.get_function(func_name, len(args))
            if bf is None:
                self.error(ErrorType.NAME_ERROR,
                           f"Function '{func_name}' with {len(args)} paremeters not found")
            return self.__exec_user_func(bf, args)

    def __eval_expr_val(self, expr):
        """
        Evaluate an expression lazily
        Eager evaluation only executed on demand
        """
        match expr.elem_type:
            # Values
            case 'int' | 'string' | 'bool':
                return BrewinValue(True, expr.get('val'))
            case 'nil':
                return BrewinValue.get_nil()
            case 'fcall':
                # list() to perform immediate lazy evaluation on arguments
                args = list(map(self.__eval_expr_val, expr.get('args')))

                # Otherwise, store fcall as need and use it later
                fcall_need = copy.deepcopy(expr)
                fcall_need.dict['args'] = args
                return BrewinValue(False, fcall_need)
            case 'var':
                return self.env.get_value(expr.get('name'))
            case 'neg' | '!':
                return self.__build_op_val(expr, ['op1']) # build_unary_expr(expr)
            case '+' | '-' | '*' | '/' | '>' | '>=' | '<' | '<=' | '&&' | '||' | '==' | '!=':
                return self.__build_op_val(expr, ['op1', 'op2']) # build_binary_expr(expr)
            case _:
                print(expr)
                self.error(ErrorType.FAULT_ERROR, "Expression operation not supported in lazy eval")

    def __build_op_val(self, expr, ops):
        # we need to copy the dict inside, otherwise, the original AST will be mutated ...
        # There are better ways to do it, but I don't care
        need = copy.deepcopy(expr)

        for op in ops:
            subexpr = expr.get(op)
            need.dict[op] = self.__eval_expr_val(subexpr)

        return BrewinValue(False, need)

    def __get_value_from_need(self, val: BrewinValue|BrewinException):
        """
        need is a BrewinValue, evaluate the need, set evaled to true and return the value
        used under eager evaluation
        """
        if isinstance(val, BrewinException):
            return val

        if val.evaled:
            return val.value
        elif val.need is None:
            self.error(ErrorType.NAME_ERROR, "Undefined variable")

        expr = val.need
        result = None
        match expr.elem_type:
            # Cannot be var, literal, only expressions or fcall are possible
            case 'fcall':
                result = self.__get_value_from_need(self.__exec_func(expr.get('name'), expr.get('args')))
            case 'neg':
                result = self.__unary_helper(expr, 'int', '-', lambda x: -x)
            case '!':
                result = self.__unary_helper(expr, 'bool', '!', lambda x: not x)
            case '+':
                result = self.__binop_helper(expr, ['int', 'string'], '+', lambda x, y: x+y)
            case '-':
                result = self.__binop_helper(expr, ['int'], '-', lambda x, y: x-y)
            case '*':
                result = self.__binop_helper(expr, ['int'], '*', lambda x, y: x*y)
            case '/':
                result = self.__binop_helper(expr, ['int'], '/', lambda x, y: x//y)
            case '>':
                result = self.__binop_helper(expr, ['int'], '>', lambda x, y: x>y)
            case '>=':
                result = self.__binop_helper(expr, ['int'], '>=', lambda x, y: x>=y)
            case '<':
                result = self.__binop_helper(expr, ['int'], '<', lambda x, y: x<y)
            case '<=':
                result = self.__binop_helper(expr, ['int'], '<=', lambda x, y: x<=y)
            case '&&':
                result = self.__shortcircuit_helper(expr, is_or=False)
            case '||':
                result = self.__shortcircuit_helper(expr, is_or=True)
            case '==':
                result = self.__eq(expr)
            case '!=':
                result = not self.__eq(expr)
            case _:
                print(expr)
                self.error(ErrorType.FAULT_ERROR, "Expression operation not supported when getting value")

        val.value = result
        val.evaled = True

        return result

    def __eval_with_type(self, expr, type, err_msg):
        """
        A wrapper of eager evaluation with type checking (more remnants from P3)
        Exception is returned regardless of type checking
        """
        result = self.__get_value_from_need(expr)
        if isinstance(result, BrewinException):
            return result

        result_typed = BrewinValue.ensure_type(result, type)
        if result_typed is not None or err_msg is None:
            return result_typed
        else:
            self.error(ErrorType.TYPE_ERROR, err_msg)

    def __exec_stmt(self, stmt):
        """
        Executes a statement
        Returns a tuple: (is_ret, ret_val), where
        * is_ret: If the current statement is a return statement
        * ret_val: The return value if present
        """
        match stmt.elem_type:
            case 'fcall':
                # list() to perform immediate lazy evaluation on arguments
                args = list(map(self.__eval_expr_val, stmt.get('args')))

                # The spec implies that we need to execute function but discard its return value
                ret = self.__exec_func(stmt.get('name'), args)

                # My old idea was wrong, I thought the function is eagerly evaluated (needing the result)
                # Strangely, this also passed the test suite (I blame the spec on not 100% clear on this)
                # ret = self.__get_value_from_need(self.__eval_expr_val(stmt))

                # Propagate exception from fcall
                if isinstance(ret, BrewinException):
                    return (True, ret)
            case 'return':
                # Evaluate expression
                expr = stmt.get('expression')
                return (True, BrewinValue.get_nil() if expr is None else self.__eval_expr_val(expr))
            case 'vardef':
                self.env.define_var(stmt.get('name'))
            case '=':
                # ATTN: If exception happens in eval, abort and throw exception
                val = self.__eval_expr_val(stmt.get('expression'))
                if isinstance(val, BrewinException):
                    return (True, val)
                self.env.assign(stmt.get('name'), val)
            case 'if':
                cond_need = self.__eval_expr_val(stmt.get('condition'))
                cond = self.__eval_with_type(cond_need, 'bool',
                                             'If condition must be boolean')
                if isinstance(cond, BrewinException):
                    return (True, cond)
                stmts = stmt.get('statements') if cond else stmt.get('else_statements')
                if stmts is not None:
                    is_ret, ret_val = self.__exec_stmts(stmts)
                    if is_ret:
                        return (True, ret_val)
            case 'for':
                # init or cond may trigger exception, e.g., i = func_that_raises()
                is_ret, ret_val = self.__exec_stmt(stmt.get('init'))
                if is_ret and isinstance(ret_val, BrewinException):
                    # can only be exception
                    return (True, ret_val)

                while True:
                    cond_need = self.__eval_expr_val(stmt.get('condition'))
                    cond = self.__eval_with_type(cond_need, 'bool',
                                                 'For condition must be boolean')
                    if isinstance(cond, BrewinException):
                        return (True, cond)

                    if not cond:
                        break
                    is_ret, ret_val = self.__exec_stmts(stmt.get('statements'))
                    if is_ret:
                        return (True, ret_val)

                    is_ret, ret_val = self.__exec_stmt(stmt.get('update'))
                    if is_ret and isinstance(ret_val, BrewinException):
                        # can only be exception
                        return (True, ret_val)
            case 'try':
                is_ret, ret_val = self.__exec_stmts(stmt.get('statements'))
                if is_ret:
                    if isinstance(ret_val, BrewinException):
                        for catch in stmt.get('catchers'):
                            if ret_val.msg == catch.get('exception_type'):
                                catch_ret, catch_retval = self.__exec_stmts(catch.get('statements'))
                                if catch_ret:
                                    return (True, catch_retval)
                                else:
                                    return (False, None)
                    # Either the code returns normally, or uncaught exception
                    return (True, ret_val)
            case 'raise':
                exc_msg_need = self.__eval_expr_val(stmt.get('exception_type'))
                exception_msg = self.__eval_with_type(exc_msg_need, 'string', 'Exception type must be a string')
                return (True, BrewinException(exception_msg))

        return (False, None)

    def __exec_stmts(self, stmts):
        """
        Execute a list of statements (for use with control flow)
        Returns value is the same as __exec_stmt
        """
        # arguments is on the outmost scope, and we allow shadowing on them
        self.env.enter_block()

        for stmt in stmts:
            is_ret, ret_val = self.__exec_stmt(stmt)
            if is_ret:
                self.env.exit_block()
                return (True, ret_val)

        self.env.exit_block()
        return (False, None)

    def __exec_user_func(self, func: BrewinProgram.BrewinFunction, args):
        self.env.enter_func()
        for formal_arg, arg in zip(func.ast.get('args'), args):
            arg_name = formal_arg.get('name')
            self.env.define_var(arg_name)
            self.env.assign(arg_name, arg)

        # we allow shadowing on arguments, __exec_stmts will open a new block to do it
        is_ret, ret_val = self.__exec_stmts(func.statements())

        if is_ret and ret_val is not None:
            self.env.exit_func()
            return ret_val
        else:
            self.env.exit_func()
            # Return default value if there is no return statement
            return BrewinValue.get_nil()

    # Intrinsics
    def __handle_input_prompts(self, args):
        if len(args) > 1:
            self.error(ErrorType.TYPE_ERROR, "input function called with > 1 parameters")
        elif len(args) == 1:
            # Only output prompt when it is in the arguments
            arg0_evaled = self.__get_value_from_need(args[0])
            self.output(self.__get_print_str(arg0_evaled))

    def __lib_inputi(self, args):
        try:
            self.__handle_input_prompts(args)
            return BrewinValue(True, int(self.get_input()))
        except BrewinPrintException as e:
            return e.exc

    def __lib_inputs(self, args):
        try:
            self.__handle_input_prompts(args)
            return BrewinValue(True, self.get_input())
        except BrewinPrintException as e:
            return e.exc

    def __lib_print(self, args):
        try:
            self.output(''.join([self.__get_print_str(self.__get_value_from_need(x)) for x in args]))
            return BrewinValue.get_nil()
        except BrewinPrintException as e:
            return e.exc

    # Operator utilities, input is already BrewinValue's need
    def __unary_helper(self, need_expr, type, op, opfunc):
        eval_result = self.__eval_with_type(need_expr.get('op1'), type,
                                            f"Operand type incompatible with unary operator '{op}'")
        # Only evaluate result if not exception
        return opfunc(eval_result) if not isinstance(eval_result, BrewinException) else eval_result

    def __binop_helper(self, need_expr, types, op, opfunc):
        # Evaluate operands once, propagate exception once seen
        op1_result = self.__get_value_from_need(need_expr.get('op1'))
        if isinstance(op1_result, BrewinException):
            return op1_result
        op2_result = self.__get_value_from_need(need_expr.get('op2'))
        if isinstance(op2_result, BrewinException):
            return op2_result

        for type in types:
            op1 = BrewinValue.ensure_type(op1_result, type)
            op2 = BrewinValue.ensure_type(op2_result, type)
            if op1 is not None and op2 is not None:
                if op == '/' and op2 == 0:
                    return BrewinException('div0')
                return opfunc(op1, op2)

        self.error(ErrorType.TYPE_ERROR, f"Operand type incompatible with unary operator '{op}'")

    def __shortcircuit_helper(self, need_expr, is_or):
        err_msg = 'Logical expression requires operands to be bool'
        op1 = self.__eval_with_type(need_expr.get('op1'), 'bool', err_msg)
        if isinstance(op1, BrewinException) or op1 == is_or:
            # short circuit
            return op1
        # Return op2 either or not it is exception
        op2 = self.__eval_with_type(need_expr.get('op2'), 'bool', err_msg)
        return op2


    def __eq(self, need_expr):
        op1 = self.__get_value_from_need(need_expr.get('op1'))
        if isinstance(op1, BrewinException):
            return op1
        op2 = self.__get_value_from_need(need_expr.get('op2'))
        if isinstance(op2, BrewinException):
            return op2

        # Poisons are already dealt with at this point
        op1_type = type(op1)
        op2_type = type(op2)

        # If types agree, values can be directly compared regardless of type
        if op1_type == op2_type:
            return op1 == op2

        return False

    def __get_print_str(self, val):
        if val is None:
            # Printing nil is undefined behavior, but we simply allow it
            # (yet another P3 relic)
            return 'nil'
        if type(val) == str:
            return val
        if type(val) == bool:
            return 'true' if val else 'false'
        if type(val) == int:
            return str(val)
        if isinstance(val, BrewinException):
            # Use python's exception to propagate brewin exception to callers
            # of this function (to simply their logic expecially for __lib_print).
            # Callers of this function will pass the brewin exception onwards
            raise BrewinPrintException(val)

        # THIS SHOULD NEVER HAPPEN
        print(val)
        self.error(ErrorType.TYPE_ERROR, "Unknown type is being printed")
