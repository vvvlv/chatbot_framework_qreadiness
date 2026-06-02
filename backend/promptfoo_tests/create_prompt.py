import json
import sys
import argparse
from promptfoo_tests.shared_state import get_prompts

# Add your files to retrieve prompts from here
import apps.quantum_readiness.maingraph
import core.graph

parser = argparse.ArgumentParser(description="This script manage prompts generation")
parser.add_argument("command")
parser.add_argument("-p", "--prompt")
parser.add_argument("promptfoo_context", nargs="*", help="Captured Promptfoo context")

def exec_prompt(args, prompt_list):
    if hasattr(args, "prompt") and args.prompt in prompt_list.keys():
        context = {}
        if args.promptfoo_context:
            try:
                json_string = args.promptfoo_context[-1]
                context = json.loads(json_string)
            except Exception as e:
                print(f"Failed to parse context : {e}", file=sys.stderr)
            try:
                print(prompt_list[args.prompt]["prompt_build"](context))
            except Exception as e:
                print(f"Failed to execute prompt generator : {e}", file=sys.stderr)
        else:
            print(f"Failed to parse context : missing context argument in the command", file=sys.stderr)
    else:
        print(f"Error: missing or invalid prompt argument in the command", file=sys.stderr)


def get_prompt(prompt_list):
    output = {key: {
        "vars": value["vars"],
        "config": value["config"]
    } for (key, value) in prompt_list.items()}
    print(json.dumps(output))


if __name__ == "__main__":
    args = parser.parse_args()
    prompt_list = get_prompts()
    if not hasattr(args, "command"):
        print(f"Error: missing command", file=sys.stderr)
    else:
        if args.command == "get_prompts":
            get_prompt(prompt_list)
        elif args.command == "exec_prompt":
            exec_prompt(args, prompt_list)
        else:
            print(f"Error: unknown command: {args.command}", file=sys.stderr)