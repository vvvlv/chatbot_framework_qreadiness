import json
import sys
import argparse
from contextlib import redirect_stdout
from promptfoo_tests.shared_state import get_prompts, VERBOSE

with redirect_stdout(sys.stderr):
    import promptfoo_tests.file_registry

parser = argparse.ArgumentParser(description="This script manage prompts generation")
parser.add_argument("command")
parser.add_argument("-p", "--prompt")
parser.add_argument("promptfoo_context", nargs="*", help="Captured Promptfoo context")

def exec_prompt(args, prompt_list, unknown):
    if hasattr(args, "prompt"):
        promptName = str(args.prompt)
        if promptName in prompt_list.keys():
            context = {}
            go = False
            if args.promptfoo_context:
                try:
                    json_string = args.promptfoo_context[-1]
                    context = json.loads(json_string)
                    go = True
                except Exception as e:
                    print(f"[EXEC {promptName}] Failed to parse context : {e}", file=sys.stderr)
            elif len(unknown) > 0:
                try:
                    json_string = unknown[-1]
                    context = json.loads(json_string)
                    go = True
                except Exception as e:
                    print(f"[EXEC {promptName}] Failed to parse context : {e}", file=sys.stderr)
            else:
                print(f"[EXEC {promptName}] Failed to parse context : missing context argument in the command", file=sys.stderr)
            if go:
                try:
                    if VERBOSE:
                        print(f"[EXEC {promptName}] context: {context}", file=sys.stderr)
                    # TODO : verify context signature
                    print(json.dumps(prompt_list[promptName]["prompt_build"](context))) # Output on stdout
                except Exception as e:
                    print(f"[EXEC {promptName}] Failed to execute prompt generator : {e}", file=sys.stderr)
        else:
            print(f"[EXEC {promptName}] Error: invalid prompt argument in the command", file=sys.stderr)
    else:
        print(f"[EXEC (?)] Error: missing or invalid prompt argument in the command", file=sys.stderr)


if __name__ == "__main__":
    args, unknown = parser.parse_known_args()
    prompt_list = get_prompts()
    if VERBOSE:
        print("[CREATE_PROMPT.PY] debug : prompt_list", prompt_list, file=sys.stderr)
    if not hasattr(args, "command"):
        print(f"[CREATE_PROMPT.PY] Error: missing command", file=sys.stderr)
    else:
        if args.command == "exec_prompt":
            exec_prompt(args, prompt_list, unknown)
        else:
            print(f"[CREATE_PROMPT.PY] Error: unknown command: {args.command}", file=sys.stderr)