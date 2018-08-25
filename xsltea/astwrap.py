import ast
import sys

_python_version = sys.version_info

if _python_version >= (3, 5):
    def Call(func, args, keywords, starargs, kws, **kwargs):
        args = list(args)
        keywords = list(keywords)
        if starargs is not None:
            args.append(ast.Starred(starargs, ast.Load(**kwargs), **kwargs))
        if kws is not None:
            keywords.append(ast.keyword(None, kws, **kwargs))
        return ast.Call(
            func,
            args,
            keywords,
            **kwargs,
        )
else:
    Call = ast.Call
