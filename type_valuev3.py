import copy
from intbase import InterpreterBase


# Enumerated type for our different language data types
class Type:
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    NIL = "nil"
    VOID = "void"


# Represents a value, which has a type and its value
class Value:
    def __init__(self, var_type, value=None):
        self.t = var_type
        self.v = value

    def value(self):
        return self.v

    def type(self):
        return self.t

class Variable:
    # var_value must be an object of type Value
    def __init__(self, var_type, var_value = None):
        self.t = var_type
        self.v = var_value
    
    def value(self):
        return self.v

    def type(self):
        return self.t

    def set_value(self, new_value):
       self.v = new_value 

class TypeManager:
    def __init__(self):
        self.__setup_valid_var_types()
        self.struct_defs = {}

    @staticmethod
    def create_value(val):
        if val == InterpreterBase.TRUE_DEF:
            return Value(Type.BOOL, True)
        elif val == InterpreterBase.FALSE_DEF:
            return Value(Type.BOOL, False)
        elif val == InterpreterBase.NIL_DEF:
            return Value(Type.NIL, None)
        elif val == InterpreterBase.VOID_DEF:
            return Value(Type.VOID, None)
        elif isinstance(val, str):
            return Value(Type.STRING, val)
        elif isinstance(val, int):
            return Value(Type.INT, val)
        else:
            raise ValueError("Unknown value type")

    def create_default_value(self, for_type):
        if for_type == Type.BOOL:
            return Value(Type.BOOL, False)
        if for_type == Type.INT:
            return Value(Type.INT, 0)
        if for_type == Type.STRING:
            return Value(Type.STRING, "")
        if for_type == Type.VOID:
            return Value(Type.VOID, None)
        if for_type == Type.NIL or for_type in self.struct_defs:
            return Value(for_type, None)

        return None

    def create_variable_with_default_value(self, for_type):
        return Variable(for_type, self.create_default_value(for_type))

    def new_struct_value(self, struct_type):
        if struct_type not in self.struct_defs:
            return None
        return Value(struct_type, copy.deepcopy(self.struct_defs[struct_type]))

    def define_struct(self, struct_ast):
        struct_type_name = struct_ast.get("name")
        fields = struct_ast.get("fields")
        if struct_type_name in self.valid_var_types or struct_type_name == Type.VOID:  
            return False 

        default_struct = {}
        # track the type name up front so the struct can self-reference it (DOCUMENT)
        self.valid_var_types.add(struct_type_name)
        self.struct_defs[struct_type_name] = default_struct
        for var_def_node in fields:
            field_name = var_def_node.get("name")
            field_type = var_def_node.get("var_type")
            default_value = Variable(field_type, self.create_default_value(field_type))
            if default_value.value() is None:
                return False
            default_struct[field_name] = default_value

        return True

    @staticmethod
    def get_printable(val):
        if val.type() == Type.INT:
            return str(val.value())
        if val.type() == Type.STRING:
            return val.value()
        if val.type() == Type.BOOL:
            if val.value() is True:
                return "true"
            return "false"
        if val.type() == Type.NIL or val.value() is None:
            return "nil"
        return None

    def valid_var_type(self, var_type):
        return var_type in self.valid_var_types

    def is_struct_type(self, var_type):
        return var_type in self.struct_defs
    
    def __setup_valid_var_types(self):
        self.valid_var_types = {Type.BOOL, Type.INT, Type.STRING}

