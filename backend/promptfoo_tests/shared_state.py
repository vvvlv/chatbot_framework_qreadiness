import sys
from typing import Dict, TypedDict, Callable, Any, Optional
import inspect
import traceback
import uuid
from pydantic import TypeAdapter

VERBOSE = False

PromptFuncType = Callable[..., str | list[Dict[str, str] | Dict[str, str]]]

class PromptSpec(TypedDict):
    prompt_build: PromptFuncType
    vars: Dict[str, Any]
    config: Dict[str, Any]

class ClassInfos(TypedDict):
    inner_func: PromptFuncType
    method: Callable
    qualname: str
    parentModule: str

prompt_registry : Dict[str, PromptSpec] = {}
to_be_revised: Dict[str, ClassInfos] = {}

def register(model: Optional[str]=None, modelConfig: Optional[Dict[str, Any]]=None) -> PromptFuncType :
    def register(ogPromptFunc: Callable) -> PromptFuncType :
        
        promptFunc = ogPromptFunc
        isMethod = False
        if isinstance(ogPromptFunc, classmethod) or isinstance(ogPromptFunc, staticmethod):
            isMethod = True
            promptFunc = ogPromptFunc.__func__

        # 1. Name the prompt
        funcName = promptFunc.__qualname__
        if funcName and funcName in prompt_registry.keys(): # avoid duplication
            print(f"[REGISTER] Rejected prompt {funcName} : name is already registered", file=sys.stderr)
            return ogPromptFunc
        if funcName is None or funcName == "":
            funcName = "none-" + str(uuid.uuid4())
        funcName = funcName.replace(".", "_")
        if "<lambda>" in funcName:
            funcName = funcName + str(uuid.uuid4())
        if VERBOSE:
            print(f"[REGISTER] Registering {funcName}...", file=sys.stderr)

        # 2. Retrieving promptFunc arguments and create JSON schema -> it will be variables for test cases
        jsonSchema = {}
        try:
            signature = inspect.signature(promptFunc)
            for name, param in signature.parameters.items():
                if name != "cls" and name != "self":
                    if not hasattr(param, "annotation") or param.annotation is inspect.Parameter.empty:
                        jsonSchema[name] = {"type": "any"}
                    else:
                        try:
                            adapter = TypeAdapter(param.annotation)
                            jsonSchema[name] = adapter.json_schema()
                        except Exception: # Don't register prompt
                            print(f"[REGISTER] Rejected prompt {funcName} : non json serializable arguments", file=sys.stderr)
                            return ogPromptFunc
        except Exception as e:
            print(f"[REGISTER] Rejected prompt {funcName}:", e, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return ogPromptFunc

        # 3. Remember methods in order to provide them their classes later
        if isMethod:
            classInfoRecord : ClassInfos = {}
            try:
                classInfoRecord["inner_func"] = promptFunc
                classInfoRecord["method"] = ogPromptFunc
                classInfoRecord["qualname"] = promptFunc.__qualname__
                classInfoRecord["parentModule"] = promptFunc.__module__
            except Exception as e:
                print(f"[REGISTER] Rejected prompt {funcName} : {e}. The function is a method, but the parent class is not found", file=sys.stderr)
                return ogPromptFunc
            to_be_revised[funcName] = classInfoRecord

        # 4. Build prompt generator for orphan functions
        def wrapped_func(context, name=funcName, vars=jsonSchema, func=promptFunc):
            vars2 = {key: value for (key, value) in context['vars'].items() if key in vars.keys()}
            print(f"[EXEC {name}] context vars: {context['vars']}", file=sys.stderr)
            prompt = func(**vars2)
            if isinstance(prompt, str):
                return [{"role": "user", "content": prompt}]
            elif isinstance(prompt, Dict) and is_message(prompt):
                return [prompt]
            elif isinstance(prompt, list) and is_message_list(prompt):
                return prompt
            else:
                raise Exception(f"Output of prompt generator {name} has invalid type (received {type(prompt)} - expected <str>, <dict[str, str]> or <list[dict[str, str]]]>) or invalid format (missing 'role' or 'content' in messages)")
            
        # 5. Register the new prompt record
        promptRecord : PromptSpec = {
            'prompt_build': wrapped_func,
            'vars': jsonSchema,
            'config': {"model": model, "modelConfig": modelConfig}
        }
        prompt_registry[funcName] = promptRecord

        # Returns input function to be a decorator
        return ogPromptFunc
    return register

def get_prompts():
    return prompt_registry

def update_prompt_func(name, new_func):
    prompt_registry[name]["prompt_build"] = new_func

def pop_prompt(name):
    prompt_registry.pop(name, None)

def get_to_be_revised():
    return to_be_revised

def is_message(d):
    return (d.get("role") in ["user", "system", "assistant", "tool"] and isinstance(d.get("content"), str))

def is_message_list(l):
    for x in l:
        if not isinstance(x, Dict) or not is_message(x):
            return False
    return True