import sys
import functools
from promptfoo_tests.shared_state import get_to_be_revised, update_prompt_func, pop_prompt, get_prompts, VERBOSE

# Add your files to retrieve prompts from here
import apps.quantum_readiness.maingraph
import core.graph

method_list = get_to_be_revised()
# print("[FILE_REGISTRY] method_list:", method_list, file=sys.stderr)
prompt_list = get_prompts()

for name in method_list:
    module = sys.modules.get(prompt_list[name]["parentModule"])
    if module is None:
        pop_prompt(name)
        print(f"[FILE_REGISTRY] ERROR : Please import the module containing {name} in file_registry.py. {name} has been removed from registered prompts", file=sys.stderr)
    else:
        # replace the unbound function with the function actually bound to the classes in its qualname
        trueFunc = functools.reduce(getattr, prompt_list[name]["qualname"].split("."), module)
        if VERBOSE:
            print(f"[FILE_REGISTRY] name: {name}, funcName: {trueFunc.__name__}", file=sys.stderr)
        prevFunc = prompt_list[name]["prompt_build"]
        def wrapped_func(context, func=trueFunc, prevFunc=prevFunc):
            return prevFunc(context, func=func)
        update_prompt_func(name, wrapped_func)