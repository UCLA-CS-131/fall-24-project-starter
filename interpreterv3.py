import copy
from enum import Enum

from brewparse import parse_program
from env_v3 import EnvironmentManager
from intbase import InterpreterBase, ErrorType
from type_valuev3 import *


class ExecStatus(Enum):
    CONTINUE = 1
    RETURN = 2


# Main interpreter class
class Interpreter(InterpreterBase):
    # constants
    NIL_VALUE = TypeManager.create_value(InterpreterBase.NIL_DEF)
    VOID_VALUE = TypeManager.create_value(InterpreterBase.VOID_DEF)
    TRUE_VALUE = TypeManager.create_value(InterpreterBase.TRUE_DEF)
    BIN_OPS = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

    # methods
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output
        self.__setup_ops()
        self.__call_stack = []
        self.type_manager = TypeManager()
        self.env = EnvironmentManager()
        self.func_name_to_ast = {}

    # run a program that's provided in a string
    # usese the provided Parser found in brewparse.py to parse the program
    # into an abstract syntax tree (ast)
    def run(self, program):
        ast = parse_program(program)
        self.__set_up_struct_table(ast)
        self.__set_up_function_table(ast)
        self.__call_func_aux("main", [])

    def __set_up_struct_table(self, ast):
        struct_asts = ast.get("structs")
        if struct_asts is None:
            return
        for struct_ast in struct_asts:
            struct_type_name = struct_ast.get("name")
            if not self.type_manager.define_struct(struct_ast):
                super().error(
                    ErrorType.TYPE_ERROR,
                    f"Invalid type when defining struct {struct_type_name}"
                )       

    def __set_up_function_table(self, ast):
        for func_def in ast.get("functions"):
            func_name = func_def.get("name")
            formal_args = func_def.get("args")
            return_type = func_def.get("return_type")
            num_params = len(formal_args)
            if func_name not in self.func_name_to_ast:
                self.func_name_to_ast[func_name] = {}
            self.func_name_to_ast[func_name][num_params] = func_def
            self.__validate_formal_parameter_types_and_return(func_name, formal_args, return_type)

    # DOCUMENT
    def __validate_formal_parameter_types_and_return(self, func_name, formal_args, return_type):
        for formal_ast in formal_args:
            arg_name = formal_ast.get("name")
            arg_type = formal_ast.get("var_type")
            if not self.type_manager.valid_var_type(arg_type):
                super().error(
                    ErrorType.TYPE_ERROR,
                    f"Invalid type for formal parameter {arg_name} in function {func_name}"
                )       
        if not self.type_manager.valid_var_type(return_type) and return_type != Type.VOID:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Invalid return type {return_type} in function {func_name}"
            )       
 

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

    def __get_return_type_of_current_function(self):
      current_func = self.__call_stack[-1]
      return current_func.get("return_type")

    def __run_statements(self, statements):
        self.env.push_block()
        for statement in statements:
            if self.trace_output:
                print(statement)
            status, return_val = self.__run_statement(statement)
            if status == ExecStatus.RETURN:
                self.env.pop_block()
                return (status, return_val)

        self.env.pop_block()
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __run_statement(self, statement):
        status = ExecStatus.CONTINUE
        return_val = None
        if statement.elem_type == InterpreterBase.FCALL_NODE:
            self.__call_func(statement)
        elif statement.elem_type == "=":
            self.__assign(statement)
        elif statement.elem_type == InterpreterBase.VAR_DEF_NODE:
            self.__var_def(statement)
        elif statement.elem_type == InterpreterBase.RETURN_NODE:
            status, return_val = self.__do_return(statement)
        elif statement.elem_type == Interpreter.IF_NODE:
            status, return_val = self.__do_if(statement)
        elif statement.elem_type == Interpreter.FOR_NODE:
            status, return_val = self.__do_for(statement)

        return (status, return_val)
    
    def __call_func(self, call_node):
        func_name = call_node.get("name")
        actual_args = call_node.get("args")
        return self.__call_func_aux(func_name, actual_args)

    def __call_func_aux(self, func_name, actual_args):
        if func_name == "print":
            return self.__call_print(actual_args)
        if func_name == "inputi" or func_name == "inputs":
            return self.__call_input(func_name, actual_args)

        func_ast = self.__get_func_by_name(func_name, len(actual_args))
        self.__call_stack.append(func_ast)
        formal_args = func_ast.get("args")
        return_type = self.__get_return_type_of_current_function()
        if len(actual_args) != len(formal_args):
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_ast.get('name')} with {len(actual_args)} args not found",
            )

        # first evaluate all of the actual parameters and associate them with the formal parameter names
        args = {}
        for formal_ast, actual_ast in zip(formal_args, actual_args):
            result = copy.copy(self.__eval_expr(actual_ast))
            arg_name = formal_ast.get("name")
            arg_type = formal_ast.get("var_type")
            if not self.__compatible_types_for_assignment(Variable(arg_type), result):
                super().error(
                    ErrorType.TYPE_ERROR,
                    f"Type mismatch on formal parameter {arg_name}"
                )
            args[arg_name] = Variable(arg_type, self.__coerce(arg_type, result))

        # then create the new activation record 
        self.env.push_func()
        # and add the formal arguments to the activation record
        for arg_name, variable in args.items():
          self.env.create(arg_name, variable)
        exec_status, return_val = self.__run_statements(func_ast.get("statements"))
        self.env.pop_func()
        self.__call_stack.pop()
        if exec_status == ExecStatus.RETURN:
            return return_val
        return self.type_manager.create_default_value(return_type)  # DOCUMENT no return statement returns default value

    def __coerce(self, target_type, value_obj):
        if target_type == Type.BOOL and value_obj.type() == Type.INT:
            return Value(Type.BOOL, bool(value_obj.value()))
        # We "coerce" nil when assigning it to an variable with declared structure type
        if self.type_manager.is_struct_type(target_type) and value_obj.type() == Type.NIL:
            return self.type_manager.create_default_value(target_type)

        return value_obj
    

    def __call_print(self, args):
        output = ""
        for arg in args:
            result = self.__eval_expr(arg)  # result is a Value object
            if result.type() == Type.VOID:
                super().error(ErrorType.TYPE_ERROR, "Void not allowed as argument")
            output = output + TypeManager.get_printable(result)  # DOCUMENT need to be able to print "nil" now, undefined for a struct
        super().output(output)
        return Interpreter.VOID_VALUE

    def __call_input(self, name, args):
        if args is not None and len(args) == 1:
            result = self.__eval_expr(args[0])
            if result.type() == Type.VOID:
                super().error(ErrorType.TYPE_ERROR, "Void not allowed as argument")
            super().output(TypeManager.get_printable(result))
        elif args is not None and len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR, "No inputi() function that takes > 1 parameter"
            )
        inp = super().get_input()
        if name == "inputi":
            return Value(Type.INT, int(inp))
        if name == "inputs":
            return Value(Type.STRING, inp)

    def __assign(self, assign_ast):
        var_name = assign_ast.get("name")
        lhs_var = self.__get_variable(var_name)
        rhs_val = self.__eval_expr(assign_ast.get("expression"))
        if not self.__compatible_types_for_assignment(lhs_var, rhs_val): # DOCUMENT
            super().error(
                ErrorType.TYPE_ERROR, f"Type mismatch {lhs_var.type()} vs {rhs_val.type()} in assignment"
            )

        # perform coercion
        if lhs_var.type() == Type.BOOL:
            rhs_val = self.__coerce(Type.BOOL, rhs_val)
        elif self.type_manager.is_struct_type(lhs_var.type()) and rhs_val.type() == Type.NIL:
            rhs_val = self.__coerce(lhs_var.type(), rhs_val)

        lhs_var.set_value(rhs_val)

    def __get_variable(self, var_name):
        split_var = var_name.split(".")
        base_var = self.env.get(split_var[0])
        if base_var is None:
            super().error(
                ErrorType.NAME_ERROR, f"Undefined variable {split_var[0]}"
            )
        while len(split_var) > 1:
            val_type = base_var.value().type()
            var_val = base_var.value().value()
            if val_type == Type.NIL or (self.type_manager.is_struct_type(val_type) and var_val is None):
                super().error(
                    ErrorType.FAULT_ERROR, f"Error dereferencing nil value {split_var[0]} in {var_name}"
                )
            if not self.type_manager.is_struct_type(val_type):
                super().error(
                    ErrorType.TYPE_ERROR, f"Dot used with non-struct {base_var} in {var_name}"
                )
            split_var.pop(0)
            base_var = var_val.get(split_var[0], None)  # var_val is a dictionary which implements the struct "field" -> Variable object
            if base_var is None:
                super().error(
                    ErrorType.NAME_ERROR, f"Unknown member {split_var[0]} in {var_name}"
                )

        return base_var
    
    def __var_def(self, var_ast):
        var_name = var_ast.get("name")
        var_type = var_ast.get("var_type")  # DOCUMENT change in AST and in syntax
        default_value = self.type_manager.create_default_value(var_type) # DOCUMENT: default value for defined variables
        variable = Variable(var_type, default_value)
        if default_value is None or not self.type_manager.valid_var_type(var_type):
            super().error(
                ErrorType.TYPE_ERROR, f"Unknown/invalid type specified {var_type}"
            )
        if not self.env.create(var_name, variable):
            super().error(
                ErrorType.NAME_ERROR, f"Duplicate definition for variable {var_name}"
            )

    def __eval_expr(self, expr_ast):
        if expr_ast.elem_type == InterpreterBase.NIL_NODE:
            return Interpreter.NIL_VALUE
        if expr_ast.elem_type == InterpreterBase.INT_NODE:
            return Value(Type.INT, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.STRING_NODE:
            return Value(Type.STRING, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.BOOL_NODE:
            return Value(Type.BOOL, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.VAR_NODE:
            var_name = expr_ast.get("name")
            variable = self.__get_variable(var_name)  # error checks
            return variable.value()
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            return self.__call_func(expr_ast)
        if expr_ast.elem_type == InterpreterBase.NEW_NODE:
            return self.__new_struct(expr_ast)
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            return self.__eval_unary_neg(expr_ast)
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            return self.__eval_unary_not(expr_ast)

    def __new_struct(self, new_ast):
        var_type = new_ast.get("var_type")
        default_value = self.type_manager.new_struct_value(var_type)
        if default_value is None:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Invalid type {var_type} for new operation",
            )
        return default_value

    def __eval_op(self, arith_ast):
        left_value_obj = self.__eval_expr(arith_ast.get("op1"))
        right_value_obj = self.__eval_expr(arith_ast.get("op2"))
       
        ltype = left_value_obj.type() 
        rtype = right_value_obj.type() 
        if ltype == rtype and ltype in self.op_to_lambda:
            f = self.op_to_lambda[ltype].get(arith_ast.elem_type)
            if f is not None:
                return f(left_value_obj, right_value_obj)

        if arith_ast.elem_type in ["==", "!="]:
            return self.__eval_compare(arith_ast.elem_type, left_value_obj, right_value_obj)

        if arith_ast.elem_type in ["||", "&&"]:
            return self.__eval_and_or(arith_ast.elem_type, left_value_obj, right_value_obj)

        super().error(
            ErrorType.TYPE_ERROR,
            f"Incompatible operator {arith_ast.elem_type} for types {left_value_obj.type()} and {right_value_obj.type()}",
        )

    def __eval_and_or(self, oper, obj1, obj2):
        # DOCUMENT:  coercion comparison rules
        type1 = obj1.type()
        type2 = obj2.type()
        if Type.VOID in (type1, type2):
            super().error(
                ErrorType.TYPE_ERROR,
                "Can't compare void type"
            )
        allowed_types = (Type.BOOL, Type.INT)
        if type1 not in allowed_types or type2 not in allowed_types:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Invalid types used with operator {oper}"
            )

        obj1 = self.__coerce(Type.BOOL, obj1)
        obj2 = self.__coerce(Type.BOOL, obj2)

        if oper == "||":
           return Value(Type.BOOL, obj1.value() or obj2.value()) 

        return Value(Type.BOOL, obj1.value() and obj2.value())

    
    def __eval_compare(self, oper, obj1, obj2):
        type1 = obj1.type()
        type2 = obj2.type()

        # No comparison allowed against void, period
        if Type.VOID in (type1, type2):
            super().error(
                ErrorType.TYPE_ERROR,
                "Can't compare void type"
            )

        # Create a comparison function based on operation == or !=
        cmp = (lambda x,y: x == y) if oper == "==" else (lambda x,y: x != y)

        # If the two types match, then just compare their values and get a result
        if type1 == type2:
           return Value(Type.BOOL, cmp(obj1.value(), obj2.value()))  # DOCUMENT that we compare object references for structs

        # Handle the case where we're comparing a valid struct to nil
        if Type.NIL in (type1, type2):
            # two literal nils already handled by the case above
            if self.type_manager.is_struct_type(type1):
                return Value(Type.BOOL, cmp(obj1.value(), None))
            elif self.type_manager.is_struct_type(type2):
                return Value(Type.BOOL, cmp(obj2.value(), None))

            # trying to compare some type other than a struct to nil; error
            super().error(
                ErrorType.TYPE_ERROR,
                "Can't compare type to nil"
            )

        # Handle the case where we're comparing int to bool, or bool to int (already handled bool to bool up above)
        # For this case we need to do our coercion to bool before comparing
        if Type.BOOL in (type1, type2):
            if Type.INT in (type1, type2):
                obj1 = self.__coerce(Type.BOOL, obj1)
                obj2 = self.__coerce(Type.BOOL, obj2)
                return Value(Type.BOOL, cmp(obj1.value(), obj2.value()))

        super().error(
            ErrorType.TYPE_ERROR,
            f"Can't compare unrelated types {type1} and {type2}"
        )

    def __compatible_types(self, oper, obj1, obj2):
        # DOCUMENT: allow comparisons ==/!= of anything against anything
        type1 = obj1.type()
        type2 = obj2.type()
        if type1 == Type.VOID or type2 == Type.VOID:
          return False
        if oper in ["==", "!="]:
            if (self.type_manager.is_struct_type(type1) and type2 == Type.NIL) or \
               (self.type_manager.is_struct_type(type2) and type1 == Type.NIL):
                return True
        if oper in ["||","&&"]:
            if (type1 == Type.INT and type2 == Type.BOOL) or \
               (type1 == Type.BOOL and type2 == Type.INT):
                return True

        return obj1.type() == obj2.type()
    
    def __compatible_types_for_assignment(self, lhs_variable, rhs_value):
        lhs_type = lhs_variable.type()
        rhs_type = rhs_value.type()
        if lhs_type == rhs_type:
            return True

        if lhs_type == Type.BOOL and rhs_type == Type.INT:
            return True

        return self.type_manager.is_struct_type(lhs_type) and rhs_value.type() == Type.NIL
        

    def __eval_unary_neg(self, arith_ast):
        value_obj = self.__eval_expr(arith_ast.get("op1"))
        if value_obj.type() != Type.INT:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )

        return Value(Type.INT, -value_obj.value())
    
    def __eval_unary_not(self, arith_ast):
        value_obj = self.__eval_expr(arith_ast.get("op1"))
        val_type = value_obj.type()

        if val_type != Type.BOOL and val_type != Type.INT:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )

        notted = Value(Type.BOOL, not self.__coerce(Type.BOOL, value_obj).value())
        return notted

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
        
        #  set up operations on void 
        self.op_to_lambda[Type.VOID] = {}


    def __do_if(self, if_ast):
        cond_ast = if_ast.get("condition")
        result = self.__eval_expr(cond_ast)
        if result.type() != Type.BOOL and result.type() != Type.INT:
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
            run_for = self.__eval_expr(cond_ast)  # check for-loop condition
            if run_for.type() != Type.BOOL and run_for.type() != Type.INT:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for for condition",
                )
            if run_for.value():
                statements = for_ast.get("statements")
                status, return_val = self.__run_statements(statements)
                if status == ExecStatus.RETURN:
                    return status, return_val

                self.__run_statement(update_ast)  # update counter variable

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_return(self, return_ast):
        expr_ast = return_ast.get("expression")
        func_ret_type = self.__get_return_type_of_current_function()
        if expr_ast is None:
            return (ExecStatus.RETURN, self.type_manager.create_default_value(func_ret_type)) # DOCUMENT return; as returning default value
        value_obj = copy.copy(self.__eval_expr(expr_ast))  # DOCUMENT
        if value_obj.type() == Type.VOID:
            super().error(
                ErrorType.TYPE_ERROR,
                "Cannot use void in return value"
            )
        if not self.__compatible_types_for_assignment(Variable(func_ret_type), value_obj):
            super().error(
                ErrorType.TYPE_ERROR,
                f"Returned value's type {value_obj.type()} is inconsistent with function's return type {func_ret_type}"
            )
        return (ExecStatus.RETURN, self.__coerce(func_ret_type, value_obj)) # DOCUMENT all coercions!
