from intbase import InterpreterBase, ErrorType
from brewparse import parse_program
from copy import deepcopy

class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)

        self.structs = {} # {name:default_init,}
        self.funcs = {} # {(name,n_args):element,}
        self.vars = [] # [({name:val,},bool),]
        self.bops = {'+', '-', '*', '/', '==', '!=', '>', '>=', '<', '<=', '||', '&&'}

    def run(self, program):
        ast = parse_program(program)

        for func in ast.get('functions'):
            self.funcs[(func.get('name'),len(func.get('args')))] = func

        for struct in ast.get('structs'):
            name = struct.get('name')

            self.structs[name] = {'t':struct.get('name'), 'f':None}

            fields = {}

            # if repeating field names, take the last one (undefined)
            for f in struct.get('fields'):
                n, t = f.get('name'), f.get('var_type')

                if t == 'int':
                    fields[n] = 0
                elif t == 'bool':
                    fields[n] = False
                elif t == 'string':
                    fields[n] = ''
                elif t in self.structs:
                    fields[n] = {'t':t, 'f':None}
                else:
                    super().error(ErrorType.TYPE_ERROR, '')

            self.structs[name]['f'] = fields

        main_key = None

        for k in self.funcs:
            if k[0] == 'main':
                main_key = k
                break

        if main_key is None:
            super().error(ErrorType.NAME_ERROR, '')

        self.run_fcall(self.funcs[main_key])

    def run_vardef(self, statement):
        name = statement.get('name')

        if name in self.vars[-1][0]:
            super().error(ErrorType.NAME_ERROR, '')

        t = statement.get('var_type')

        if t == 'int':
            self.vars[-1][0][name] = 0
        elif t == 'bool':
            self.vars[-1][0][name] = False
        elif t == 'string':
            self.vars[-1][0][name] = ''
        elif t in self.structs:
            self.vars[-1][0][name] = {'t':t, 'f':None}
        else:
            super().error(ErrorType.TYPE_ERROR, '')

    def run_assign(self, statement):
        split_name = statement.get('name').split('.')
        name, field_nest = split_name[0], split_name[1:]

        for scope_vars, is_func in self.vars[::-1]:
            if name in scope_vars:
                out = self.run_expr(statement.get('expression'))

                for i,field in enumerate(split_name[:-1]):
                    if type(scope_vars[field]) != dict:
                        super().error(ErrorType.TYPE_ERROR, '')

                    if scope_vars[field]['f'] is None:
                        super().error(ErrorType.FAULT_ERROR, '')

                    scope_vars = scope_vars[field]['f']
                    name = field_nest[i]

                    if name not in scope_vars:
                        super().error(ErrorType.NAME_ERROR, '')

                tl, tr = type(scope_vars[name]), type(out)

                if tl != tr or (tl == tr == dict and (scope_vars[name]['t'] != out['t'])):
                    if tl == bool and tr == int:
                        out = bool(out)
                    elif tl == tr == dict:
                        if out['f'] is None:
                            out['t'] = scope_vars[name]['t']
                        if scope_vars[name]['t'] is None:
                            pass
                    else:
                        super().error(ErrorType.TYPE_ERROR, '')

                scope_vars[name] = out

                return

            if is_func: break

        super().error(ErrorType.NAME_ERROR, '')

    def run_fcall(self, statement):
        fcall_name, args = statement.get('name'), statement.get('args')

        if fcall_name == 'inputi' or fcall_name == 'inputs':
            if len(args) > 1:
                super().error(ErrorType.NAME_ERROR, '')

            if args:
                super().output(str(self.run_expr(args[0])))

            res = super().get_input()

            return int(res) if fcall_name == 'inputi' else res

        if fcall_name == 'print':
            out = ''

            for arg in args:
                c_out = self.run_expr(arg)
                if c_out is None:
                    super().error(ErrorType.TYPE_ERROR, '')
                elif type(c_out) == dict:
                    out += 'nil'
                elif type(c_out) == bool:
                    out += str(c_out).lower()
                else:
                    out += str(c_out)

            super().output(out)

            return None
        
        if (fcall_name, len(args)) not in self.funcs:
            super().error(ErrorType.NAME_ERROR, '')

        func_def = self.funcs[(fcall_name, len(args))]

        template_args = [a.get('name') for a in func_def.get('args')]
        passed_args = [self.run_expr(a) for a in args]

        template_args_t = [a.get('var_type') for a in func_def.get('args')]
        passed_args_t = [type(self.run_expr(a)) for a in args]

        valid = True
        for i, (tt, pt) in enumerate(zip(template_args_t, passed_args_t)):
            if tt == 'string':
                if pt != str:
                    valid = False
                    break
            elif tt == 'int':
                if pt != int:
                    valid = False
                    break
            elif tt == 'bool':
                if pt != bool:
                    if pt == int:
                        passed_args[i] = bool(passed_args[i])
                    else:
                        valid = False
                        break
            elif pt == dict:
                if passed_args[i] == {'t':None, 'f':None}:
                    if tt not in self.structs:
                        valid = False
                    break
                elif passed_args[i]['t'] != tt:
                    valid = False
                    break

        if not valid:
            super().error(ErrorType.TYPE_ERROR, '')

        ret_type = func_def.get('return_type')

        self.vars.append(({k:v for k,v in zip(template_args, passed_args)}, True))
        res, ret = self.run_statements(func_def.get('statements'), ret_type)
        self.vars.pop()

        if not ret:
            res = self.run_return(None, ret_type)

        return res

    def run_if(self, statement, ret_type):
        cond = self.run_expr(statement.get('condition'))

        if not (type(cond) == bool or type(cond) == int):
            super().error(ErrorType.TYPE_ERROR, '')

        self.vars.append(({}, False))

        res, ret = None, False

        if cond:
            res, ret = self.run_statements(statement.get('statements'), ret_type)
        elif statement.get('else_statements'):
            res, ret = self.run_statements(statement.get('else_statements'), ret_type)

        self.vars.pop()

        return res, ret

    def run_for(self, statement, ret_type):
        res, ret = None, False

        self.run_assign(statement.get('init'))

        while True:
            cond = self.run_expr(statement.get('condition'))

            if not (type(cond) == bool or type(cond) == int):
                super().error(ErrorType.TYPE_ERROR, '')

            if ret or not cond: break

            self.vars.append(({}, False))
            res, ret = self.run_statements(statement.get('statements'), ret_type)
            self.vars.pop()

            self.run_assign(statement.get('update'))

        return res, ret

    def run_return(self, statement, ret_type):
        expr = statement.get('expression') if statement else None

        if expr:
            expr = self.run_expr(expr)

        if ret_type == 'string':
            if expr is None:
                return ''
            elif type(expr) == str:
                return expr
        elif ret_type == 'int':
            if expr is None:
                return 0
            elif type(expr) == int:
                return expr
        elif ret_type == 'bool':
            if expr is None:
                return False
            elif type(expr) == bool:
                return expr
            elif type(expr) == int:
                return bool(expr)
        elif ret_type == 'void':
            if expr is None:
                return None
        else:
            if expr is None and ret_type in self.structs:
                return {'t':ret_type, 'f':None}
            elif type(expr) == dict and expr['t'] == ret_type:
                return expr

        super().error(ErrorType.TYPE_ERROR, '')

    def run_statements(self, statements, ret_type):
        res, ret = None, False

        for statement in statements:
            kind = statement.elem_type

            if kind == 'vardef':
                self.run_vardef(statement)
            elif kind == '=':
                self.run_assign(statement)
            elif kind == 'fcall':
                self.run_fcall(statement)
            elif kind == 'if':
                res, ret = self.run_if(statement, ret_type)
                if ret: break
            elif kind == 'for':
                res, ret = self.run_for(statement, ret_type)
                if ret: break
            elif kind == 'return':
                res = self.run_return(statement, ret_type)
                ret = True
                break

        return res, ret

    def run_expr(self, expr):
        kind = expr.elem_type

        if kind == 'new':
            struct = expr.get('var_type')

            if struct in self.structs:
                return deepcopy(self.structs[struct])

            super().error(ErrorType.TYPE_ERROR, '')

        elif kind == 'nil':
            return {'t':None, 'f':None}

        elif kind == 'int' or kind == 'string' or kind == 'bool':
            return expr.get('val')

        elif kind == 'var':
            split_name = expr.get('name').split('.')
            name, field_nest = split_name[0], split_name[1:]

            for scope_vars, is_func in self.vars[::-1]:
                if name in scope_vars:
                    for i,field in enumerate(split_name[:-1]):
                        if type(scope_vars[field]) != dict:
                            super().error(ErrorType.TYPE_ERROR, '')

                        if scope_vars[field]['f'] is None:
                            super().error(ErrorType.FAULT_ERROR, '')

                        scope_vars = scope_vars[field]['f']
                        name = field_nest[i]

                        if name not in scope_vars:
                            super().error(ErrorType.NAME_ERROR, '')

                    return scope_vars[name]

                if is_func: break

            super().error(ErrorType.NAME_ERROR, '')

        elif kind == 'fcall':
            return self.run_fcall(expr)

        elif kind in self.bops:
            l, r = self.run_expr(expr.get('op1')), self.run_expr(expr.get('op2'))
            tl, tr = type(l), type(r)

            if tl == tr == dict:
                if l['f'] is None or r['f'] is None:
                    if kind == '==': return l['f'] is r['f']
                    if kind == '!=': return l['f'] is not r['f']
                elif l['t'] == r['t']:
                    if kind == '==': return l is r
                    if kind == '!=': return l is not r

            if tl == tr:
                if kind == '==': return l == r
                if kind == '!=': return l != r

            if tl == tr == str:
                if kind == '+': return l + r

            if tl == tr == int:
                if kind == '+': return l + r
                if kind == '-': return l - r
                if kind == '*': return l * r
                if kind == '/': return l // r
                if kind == '<': return l < r
                if kind == '<=': return l <= r
                if kind == '>': return l > r
                if kind == '>=': return l >= r
            
            if tl in {bool, int} and tr in {bool, int}:
                if kind == '&&': return bool(l) and bool(r)
                if kind == '||': return bool(l) or bool(r)
                if kind == '==': return bool(l) == bool(r)
                if kind == '!=': return bool(l) != bool(r)

            super().error(ErrorType.TYPE_ERROR, '')

        elif kind == 'neg':
            o = self.run_expr(expr.get('op1'))
            if type(o) == int: return -o
            
            super().error(ErrorType.TYPE_ERROR, '')

        elif kind == '!':
            o = self.run_expr(expr.get('op1'))
            if type(o) == bool or type(o) == int: return not o

            super().error(ErrorType.TYPE_ERROR, '')

        return None

def main():
    interpreter = Interpreter()

    with open('./test.br', 'r') as f:
        program = f.read()

    interpreter.run(program)

if __name__ == '__main__':
    main()
