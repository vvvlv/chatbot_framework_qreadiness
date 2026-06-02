from typing import Dict, TypedDict, Callable, Any, Optional
from types import GenericAlias
import inspect
import traceback
import uuid
import sys
from pydantic import TypeAdapter

PromptFuncType = Callable[[Dict[str, Any]], str | list[Dict[str, str] | Dict[str, str]]]

class PromptSpec(TypedDict):
    prompt_build: PromptFuncType
    vars: Dict[str, Any]
    config: Dict[str, Any]

prompt_registry : Dict[str, PromptSpec] = {}

def register(model: Optional[str]=None, modelConfig: Optional[Dict]=None) -> PromptFuncType :
    def register(promptFunc: PromptFuncType) -> PromptFuncType :

        # 1. Name the prompt
        funcName = promptFunc.__qualname__
        if funcName in prompt_registry.keys(): # avoid duplication
            return promptFunc
        if funcName is None or funcName == "<lambda>" or funcName == "":
            funcName = str(uuid.uuid4())
        print(f"Registering {funcName}...", file=sys.stderr)

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
                            return promptFunc
        except Exception as e:
            print("Warning:", e)
            traceback.print_exc()
        print(f"args of {funcName}: {jsonSchema}", file=sys.stderr)

        # 3. Build prompt generator
        def wrapped_func(context):
            vars = context['vars']
            config = {}
            for (key, value) in modelConfig.items():
                if key in vars.keys():
                    config[key] = vars[key]
                else:
                    config[key] = value
            return {
                "prompt": promptFunc(**vars),
                "config": config,
            }
        
        # 4. Register the new prompt record
        promptRecord : PromptSpec = {
            'prompt_build': wrapped_func,
            'vars': jsonSchema,
            'config': {**kwargs}
        }
        prompt_registry[funcName] = promptRecord
        print("Updated prompt_registry :", prompt_registry, file=sys.stderr)

        # Returns input function to be a decorator
        return promptFunc
    return register

def get_prompts():
    return prompt_registry