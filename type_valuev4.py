from intbase import InterpreterBase

# Enumerated type for our different language data types
class Type:
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    NIL = "nil"


class ValueBase:
    def __init__(self):
        pass

    def value(self):
        pass

    def type(self):
        pass

    def evaluated(self):
        return True


# Represents a value, which has a type and its value
class Value(ValueBase):
    def __init__(self, type, value=None):
        self.t = type
        self.v = value

    def value(self):
        return self.v

    def type(self):
        return self.t
    
    def __str__(self) -> str:
        return f"Value({self.t}, {self.v})"
    
class LazyValue(ValueBase):
    def __init__(self, ast_expr, top_env):
        self.ast_expr = ast_expr
        self.top_env = top_env
        self.eval = False
        self.v = None
        self.t = None

    def set_type_value(self, t, v):
        self.eval = True
        self.top_env = None
        self.t = t
        self.v = v

    def evaluated(self):
        return self.eval

    def value(self):
        if not self.eval:
            raise ValueError("Lazy evaluation not yet implemented")
        return self.v

    def type(self):
        if not self.eval:
            raise ValueError("Lazy evaluation not yet implemented")
        return self.t
    
    def env(self):
        return self.top_env
    
    def ast(self):
        return self.ast_expr
    


def create_value(val):
    if val == InterpreterBase.TRUE_DEF:
        return Value(Type.BOOL, True)
    elif val == InterpreterBase.FALSE_DEF:
        return Value(Type.BOOL, False)
    elif val == InterpreterBase.NIL_DEF:
        return Value(Type.NIL, None)
    elif isinstance(val, str):
        return Value(Type.STRING, val)
    elif isinstance(val, int):
        return Value(Type.INT, val)
    else:
        raise ValueError("Unknown value type")


def get_printable(val):
    if val.type() == Type.INT:
        return str(val.value())
    if val.type() == Type.STRING:
        return val.value()
    if val.type() == Type.BOOL:
        if val.value() is True:
            return "true"
        return "false"
    return None
