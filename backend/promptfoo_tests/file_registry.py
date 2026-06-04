import sys
import functools
from promptfoo_tests.shared_state import get_to_be_revised, update_prompt_func, pop_prompt, get_prompts, VERBOSE

# Add your files to retrieve prompts from here
import apps.quantum_readiness.maingraph
import core.graph

method_list = get_to_be_revised()
# print("[FILE_REGISTRY] method_list:", method_list, file=sys.stderr)
prompt_list = get_prompts()

for (name, record) in method_list.items():
    module = sys.modules.get(record["parentModule"])
    if module is None:
        pop_prompt(name)
        print(f"[FILE_REGISTRY] ERROR : Please import the module containing {name} in file_registry.py. {name} has been removed from registered prompts", file=sys.stderr)
    else:
        trueFunc = functools.reduce(getattr, record["qualname"].split("."), module)
        if VERBOSE:
            print(f"[FILE_REGISTRY] name: {name}, funcName: {trueFunc.__name__}", file=sys.stderr)
        prevFunc = prompt_list[name]["prompt_build"]
        def wrapped_func(context, func=trueFunc, prevFunc=prevFunc):
            return prevFunc(context, func=func)
        update_prompt_func(name, wrapped_func)