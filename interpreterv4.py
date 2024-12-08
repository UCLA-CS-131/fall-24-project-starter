import copy
from enum import Enum

from brewparse import parse_program
from env_v4 import EnvironmentManager
from intbase import InterpreterBase, ErrorType
from type_valuev4 import Type, Value, LazyValue, create_value, get_printable


class ExecStatus(Enum):
    CONTINUE = 1
    RETURN = 2
    EXCEPTION = 3


# Main interpreter class
class Interpreter(InterpreterBase):
    # constants
    NIL_VALUE = create_value(InterpreterBase.NIL_DEF)
    TRUE_VALUE = create_value(InterpreterBase.TRUE_DEF)
    DIV_ZERO = Value(Type.STRING, "div0")
    BIN_OPS = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

    # methods
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output
        self.__setup_ops()

    # run a program that's provided in a string
    # usese the provided Parser found in brewparse.py to parse the program
    # into an abstract syntax tree (ast)
    def run(self, program):
        ast = parse_program(program)
        self.__set_up_function_table(ast)
        self.env = EnvironmentManager()
        status, result = self.__call_func_aux("main", [])
        if status == ExecStatus.EXCEPTION:
            super().error(ErrorType.FAULT_ERROR, f"Exception {result.value()} not caught!")


    def __set_up_function_table(self, ast):
        self.func_name_to_ast = {}
        for func_def in ast.get("functions"):
            func_name = func_def.get("name")
            num_params = len(func_def.get("args"))
            if func_name not in self.func_name_to_ast:
                self.func_name_to_ast[func_name] = {}
            self.func_name_to_ast[func_name][num_params] = func_def

    def __get_func_by_name(self, name, num_params):
        if name not in self.func_name_to_ast:
            super().error(ErrorType.NAME_ERROR, f"Function {name} not found")
        candidate_funcs = self.func_name_to_ast[name]
        if num_params not in candidate_funcs:
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {name} taking {num_params} params not found",
            )
        return candidate_funcs[num_params]

    def __run_statements(self, statements):
        self.env.push_block()
        for statement in statements:
            if self.trace_output:
                print(statement)
            status, return_val = self.__run_statement(statement)
            if status == ExecStatus.RETURN or status == ExecStatus.EXCEPTION:
                self.env.pop_block()
                return (status, return_val)

        self.env.pop_block()
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __run_statement(self, statement):
        status = ExecStatus.CONTINUE
        return_val = None
        if statement.elem_type == InterpreterBase.FCALL_NODE:
            status, return_val = self.__call_func(statement)
        elif statement.elem_type == "=":
            status, return_val = self.__assign(statement)
        elif statement.elem_type == InterpreterBase.VAR_DEF_NODE:
            self.__var_def(statement)
        elif statement.elem_type == InterpreterBase.RETURN_NODE:
            status, return_val = self.__do_return(statement)
        elif statement.elem_type == InterpreterBase.RAISE_NODE:
            status, return_val = self.__do_raise(statement)
        elif statement.elem_type == Interpreter.IF_NODE:
            status, return_val = self.__do_if(statement)
        elif statement.elem_type == Interpreter.FOR_NODE:
            status, return_val = self.__do_for(statement)
        elif statement.elem_type == Interpreter.TRY_NODE:
            status, return_val = self.__do_try(statement)

        return (status, return_val)

    def __call_func(self, call_node):
        func_name = call_node.get("name")
        actual_args = call_node.get("args")
        status, return_val = self.__call_func_aux(func_name, actual_args)
        if status == ExecStatus.EXCEPTION:
            return (status, return_val)  # return_val is the exception type
        if status == ExecStatus.RETURN:
            status = ExecStatus.CONTINUE
        return (status, return_val)

    def __call_func_aux(self, func_name, actual_args):
        if func_name == "print":
            return self.__call_print(actual_args)
        if func_name == "inputi" or func_name == "inputs":
            return self.__call_input(func_name, actual_args)

        func_ast = self.__get_func_by_name(func_name, len(actual_args))
        formal_args = func_ast.get("args")
        if len(actual_args) != len(formal_args):
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_ast.get('name')} with {len(actual_args)} args not found",
            )

        # first evaluate all of the actual parameters and associate them with the formal parameter names
        args = {}
        for formal_ast, actual_ast in zip(formal_args, actual_args):
            status, actual_arg = self.__eval_expr(actual_ast)
            if status == ExecStatus.EXCEPTION:
                return (status, actual_arg)
            result = copy.copy(actual_arg)
            arg_name = formal_ast.get("name")
            args[arg_name] = result

        # then create the new activation record
        self.env.push_func()
        # and add the formal arguments to the activation record
        for arg_name, value in args.items():
          self.env.create(arg_name, value)
        status, return_val = self.__run_statements(func_ast.get("statements"))
        self.env.pop_func()
        #print(f"call_func_aux: status: {status}, return_val: {return_val}")
        return (status, return_val)

    # document that print is all or nothing. if an exception occurs, then the output is not printed
    def __call_print(self, args):
        output = ""
        for arg in args:
            status, result = self.__eval_expr(arg, True)  # result is a Value object   # document forced evaluation
            if status == ExecStatus.EXCEPTION:
                return (status, result) # result is the exception type
            output = output + get_printable(result)
        super().output(output)
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __call_input(self, name, args):
        if args is not None and len(args) == 1:
            status, result = self.__eval_expr(args[0], True) # document forced evaluation
            if status == ExecStatus.EXCEPTION:
                return (status, result)
            super().output(get_printable(result))
        elif args is not None and len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR, "No inputi() function that takes > 1 parameter"
            )
        inp = super().get_input()
        if name == "inputi":
            return (ExecStatus.CONTINUE, Value(Type.INT, int(inp)))
        if name == "inputs":
            return (ExecStatus.CONTINUE, Value(Type.STRING, inp))

    def __assign(self, assign_ast):
        var_name = assign_ast.get("name")
        status, value_obj = self.__eval_expr(assign_ast.get("expression"))
        if status == ExecStatus.EXCEPTION:
            return (status, value_obj)

        if not self.env.set(var_name, value_obj):
            super().error(
                ErrorType.NAME_ERROR, f"Undefined variable {var_name} in assignment"
            )
        return (status, value_obj)

    def __var_def(self, var_ast):
        var_name = var_ast.get("name")
        if not self.env.create(var_name, Interpreter.NIL_VALUE):
            super().error(
                ErrorType.NAME_ERROR, f"Duplicate definition for variable {var_name}"
            )

    # document that all type checking of lazy expressions is done only at the time of evaluation
    # document that all binary expressions are evaluated from left to right and so an exception on the first one will prevent the second one from being evaluated

    def __eval_expr(self, expr_ast, eager = False):
        if expr_ast.elem_type == InterpreterBase.NIL_NODE:
            return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)
        if expr_ast.elem_type == InterpreterBase.INT_NODE:
            return (ExecStatus.CONTINUE, Value(Type.INT, expr_ast.get("val")))
        if expr_ast.elem_type == InterpreterBase.STRING_NODE:
            return (ExecStatus.CONTINUE, Value(Type.STRING, expr_ast.get("val")))
        if expr_ast.elem_type == InterpreterBase.BOOL_NODE:
            return (ExecStatus.CONTINUE, Value(Type.BOOL, expr_ast.get("val")))

        if eager is False:
            #print(f"delaying evaluation: {expr_ast.elem_type}")
            #if (expr_ast.elem_type == "fcall"):
            #    print("funcname: ", expr_ast.get("name"))
            return (ExecStatus.CONTINUE, LazyValue(expr_ast, self.env.get_top_env()))

        #print(f"forcing evaluation: {expr_ast.elem_type}")
        #if (expr_ast.elem_type == "fcall"):
        #    print("funcname: ", expr_ast.get("name"))

        if expr_ast.elem_type == InterpreterBase.VAR_NODE:
            var_name = expr_ast.get("name")
            val = self.env.get(var_name)
            if val is None:
                super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            return self.__evaluate_if_necessary(val, eager)
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            status, result = self.__call_func(expr_ast)
            #print(f"FCALL: status: {status}, result: {result}")
            if status == ExecStatus.EXCEPTION:
                return (status, result) # result is the exception type
            return self.__evaluate_if_necessary(result, True)
        # document that all binary operations must be evaluated from left to right when they are evaluated
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            return self.__eval_unary(expr_ast, Type.INT, lambda x: -1 * x)
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            return self.__eval_unary(expr_ast, Type.BOOL, lambda x: not x)

    def __evaluate_if_necessary(self, val, eager):
        if val.evaluated() or not eager:
            #if val.evaluated() and type(val.value()) == LazyValue:
            #   print("Reusing cached value: ", val.value())
            return (ExecStatus.CONTINUE, val)

        #print("eval if necessary")
        env_to_eval = val.env()
        self.env.push_func(env_to_eval)
        status, evaluated_val = self.__eval_expr(val.ast(), True)

        # cache result
        #print("Caching result: ", evaluated_val.value())
        if status != ExecStatus.EXCEPTION:
            val.set_type_value(evaluated_val.type(), evaluated_val.value())
            status = ExecStatus.CONTINUE

        self.env.pop_func()
        return (status, evaluated_val)

    def __eval_op(self, arith_ast):
        if arith_ast.elem_type in ["||", "&&"]:
            return self.__eval_logical(arith_ast)

        left_status, left_value_obj = self.__eval_expr(arith_ast.get("op1"), True)
        if left_status == ExecStatus.EXCEPTION:
            return (ExecStatus.EXCEPTION, left_value_obj) # document: evaluate left side first so if both would throw execptions, only left gets thrown

        right_status, right_value_obj = self.__eval_expr(arith_ast.get("op2"), True)
        if right_status == ExecStatus.EXCEPTION:
            return (ExecStatus.EXCEPTION, right_value_obj)

        if not self.__compatible_types(
            arith_ast.elem_type, left_value_obj, right_value_obj
        ):
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for {arith_ast.elem_type} operation",
            )
        if arith_ast.elem_type not in self.op_to_lambda[left_value_obj.type()]:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible operator {arith_ast.elem_type} for type {left_value_obj.type()}",
            )
        f = self.op_to_lambda[left_value_obj.type()][arith_ast.elem_type]

        #print(f"evaluating binary: {left_value_obj.value()} {arith_ast.elem_type} {right_value_obj.value()}")
        if arith_ast.elem_type == "/" and right_value_obj.value() == 0:  # document div0 exception
            return (ExecStatus.EXCEPTION, Interpreter.DIV_ZERO)

        return (ExecStatus.CONTINUE, f(left_value_obj, right_value_obj))

    def __eval_logical(self, arith_ast):
        left_status, left_value_obj = self.__eval_expr(arith_ast.get("op1"), True)
        if left_status == ExecStatus.EXCEPTION:
            return (ExecStatus.EXCEPTION, left_value_obj)
        if left_value_obj.type() != Type.BOOL:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )
        if (arith_ast.elem_type == "||" and left_value_obj.value()):
            return (ExecStatus.CONTINUE, Value(Type.BOOL, True))
        elif (arith_ast.elem_type == "&&" and not left_value_obj.value()):
            return (ExecStatus.CONTINUE, Value(Type.BOOL, False))
        else:
            right_status, right_value_obj = self.__eval_expr(arith_ast.get("op2"), True)
            if right_status == ExecStatus.EXCEPTION:
                return (ExecStatus.EXCEPTION, right_value_obj)
            if right_value_obj.type() != Type.BOOL:
                super().error(
                    ErrorType.TYPE_ERROR,
                    f"Incompatible type for {arith_ast.elem_type} operation",
                )
            # the right side was guaranteed to be false for || and true for &&, so all we need to do is return the right_value_obj now
            # for ||, if the right side is true, then the whole expression is true
            # for &&, if the right side is false, then the whole expression is false
            return (ExecStatus.CONTINUE, right_value_obj)

    def __compatible_types(self, oper, obj1, obj2):
        # DOCUMENT: allow comparisons ==/!= of anything against anything
        if oper in ["==", "!="]:
            return True
        return obj1.type() == obj2.type()

    def __eval_unary(self, arith_ast, t, f):
        status, value_obj = self.__eval_expr(arith_ast.get("op1"), True)
        #print(f"evaluating unary: {status} {value_obj.value()} {value_obj.type()}")
        if status == ExecStatus.EXCEPTION:
            return (ExecStatus.EXCEPTION, value_obj)

        if value_obj.type() != t:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )
        return (ExecStatus.CONTINUE, Value(t, f(value_obj.value())))

    def __setup_ops(self):
        self.op_to_lambda = {}
        # set up operations on integers
        self.op_to_lambda[Type.INT] = {}
        self.op_to_lambda[Type.INT]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.INT]["-"] = lambda x, y: Value(
            x.type(), x.value() - y.value()
        )
        self.op_to_lambda[Type.INT]["*"] = lambda x, y: Value(
            x.type(), x.value() * y.value()
        )
        self.op_to_lambda[Type.INT]["/"] = lambda x, y: Value(
            x.type(), x.value() // y.value()
        )
        self.op_to_lambda[Type.INT]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.INT]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )
        self.op_to_lambda[Type.INT]["<"] = lambda x, y: Value(
            Type.BOOL, x.value() < y.value()
        )
        self.op_to_lambda[Type.INT]["<="] = lambda x, y: Value(
            Type.BOOL, x.value() <= y.value()
        )
        self.op_to_lambda[Type.INT][">"] = lambda x, y: Value(
            Type.BOOL, x.value() > y.value()
        )
        self.op_to_lambda[Type.INT][">="] = lambda x, y: Value(
            Type.BOOL, x.value() >= y.value()
        )
        #  set up operations on strings
        self.op_to_lambda[Type.STRING] = {}
        self.op_to_lambda[Type.STRING]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.STRING]["=="] = lambda x, y: Value(
            Type.BOOL, x.value() == y.value()
        )
        self.op_to_lambda[Type.STRING]["!="] = lambda x, y: Value(
            Type.BOOL, x.value() != y.value()
        )
        #  set up operations on bools
        self.op_to_lambda[Type.BOOL] = {}

        self.op_to_lambda[Type.BOOL]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.BOOL]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )

        #  set up operations on nil
        self.op_to_lambda[Type.NIL] = {}
        self.op_to_lambda[Type.NIL]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.NIL]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )

    def __do_if(self, if_ast):
        cond_ast = if_ast.get("condition")
        status, result = self.__eval_expr(cond_ast, True) # document forced evaluation
        if status == ExecStatus.EXCEPTION:
            return (status, result)

        if result.type() != Type.BOOL:
            super().error(
                ErrorType.TYPE_ERROR,
                "Incompatible type for if condition",
            )
        if result.value():
            statements = if_ast.get("statements")
            status, return_val = self.__run_statements(statements)
            return (status, return_val)
        else:
            else_statements = if_ast.get("else_statements")
            if else_statements is not None:
                status, return_val = self.__run_statements(else_statements)
                return (status, return_val)

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_for(self, for_ast):
        init_ast = for_ast.get("init")
        cond_ast = for_ast.get("condition")
        update_ast = for_ast.get("update")

        self.__run_statement(init_ast)  # initialize counter variable
        run_for = Interpreter.TRUE_VALUE
        while run_for.value():
            status, run_for = self.__eval_expr(cond_ast, True)  # check for-loop condition # document forced evaluation
            if status == ExecStatus.EXCEPTION:
                return (status, run_for)

            if run_for.type() != Type.BOOL:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for for condition",
                )
            if run_for.value():
                statements = for_ast.get("statements")
                status, return_val = self.__run_statements(statements)
                if status == ExecStatus.RETURN or status == ExecStatus.EXCEPTION:
                    return status, return_val
                self.__run_statement(update_ast)  # update counter variable

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    # document return expression is lazy
    def __do_return(self, return_ast):
        expr_ast = return_ast.get("expression")
        if expr_ast is None:
            return (ExecStatus.RETURN, Interpreter.NIL_VALUE)
        status, ret_val = self.__eval_expr(expr_ast)
        if status == ExecStatus.EXCEPTION:
            return (status, ret_val)
        return (ExecStatus.RETURN, copy.copy(ret_val))

    # document we will never raise in an expression used by a raise (e.g. raise foo(), foo() will never raise itself)
    # document that raise argument evaluation is eager
    def __do_raise(self, return_ast):
        expr_ast = return_ast.get("exception_type")
        #print("RAISE: ", expr_ast)
        _, exception_type = self.__eval_expr(expr_ast, True)
        value_obj = copy.copy(exception_type)
        if exception_type.type() != Type.STRING:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Invalid type for raise argument: {value_obj.type()}",
            )
        return (ExecStatus.EXCEPTION, value_obj)

    def __do_try(self, try_ast):
        statements = try_ast.get("statements")
        status, return_val = self.__run_statements(statements)
        if status != ExecStatus.EXCEPTION:
            return (status, return_val)
        catchers = try_ast.get("catchers")
        for catcher_ast in catchers:
            exception_type = catcher_ast.get("exception_type")
            if return_val.value() == exception_type:
                return self.__run_statements(catcher_ast.get("statements"))

        # propagate error
        return (status, return_val)
