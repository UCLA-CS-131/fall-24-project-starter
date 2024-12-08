import copy

import type_valuev4

# The EnvironmentManager class keeps a mapping between each variable name (aka symbol)
# in a brewin program and the Value object, which stores a type, and a value.
class EnvironmentManager:
    def __init__(self):
        self.environment = []

    # returns a VariableDef object
    def get(self, symbol):
        cur_func_env = self.environment[-1]
        for env in reversed(cur_func_env):
            if symbol in env:
                return env[symbol]

        return None

    def set(self, symbol, value):
        cur_func_env = self.environment[-1]
        for env in reversed(cur_func_env):
            if symbol in env:
                env[symbol] = value
                return True

        return False

    # create a new symbol in the top-most environment, regardless of whether that symbol exists
    # in a lower environment
    def create(self, symbol, value):
        cur_func_env = self.environment[-1]
        if symbol in cur_func_env[-1]:   # symbol already defined in current scope
            return False
        cur_func_env[-1][symbol] = value
        return True

    # used when we enter a new function - start with empty dictionary to hold parameters.
    def push_func(self, func_env = None):
        if func_env is None:
            self.environment.append([{}])  # [[...]] -> [[...], [{}]]
        else:
            self.environment.append(func_env) # used for lazy evaluation

    def push_block(self):
        cur_func_env = self.environment[-1]
        cur_func_env.append({})  # [[...],[{....}] -> [[...],[{...}, {}]]

    def pop_block(self):
        cur_func_env = self.environment[-1]
        cur_func_env.pop() 

    # used when we exit a nested block to discard the environment for that block
    def pop_func(self):
        self.environment.pop()

    # return a new environment that only includes the top function's environment/in-scope variables
    def get_top_env(self):
        c = self.__env_copy(self.environment[-1])
        #print("ENV: ")
        #self.print_env(c)
        return c

    def __env_copy(self, top_level_env):
        new_env = []
        for d in top_level_env:
            new_env.append(d.copy())
        return new_env
    
    # write a function to recursively print the environment
    def print_env(self, env):
        def print_recursive(obj, indent=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    print(f"{indent}{key}:")
                    print_recursive(value, indent + "  ")
            elif isinstance(obj, list):
                for item in obj:
                    print_recursive(item, indent + "  ")
            elif isinstance(obj, type_valuev4.LazyValue):
                print(f"{indent}LazyValue: ")    
                print_recursive(obj.top_env, indent + "  ")
            elif isinstance(obj, type_valuev4.Value):
                print(f"{indent}{obj.type()}: {obj.value()}")
            else:
                print(f"---{indent}{obj}")

        for e in env:
            for k, v in e.items():
                print(f"{k}:")
                print_recursive(v, "  ")
        
