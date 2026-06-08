import json
import re
from pathlib import Path
import argparse
from promptfoo_tests.shared_state import get_prompts
import promptfoo_tests.file_registry

python_path = "C:/Users/clord/AppData/Local/Programs/Python/Python311/python.exe"

parser = argparse.ArgumentParser(description="Script to generate promptfoo config files")
parser.add_argument("command")
parser.add_argument('--prompt')
parser.add_argument('--name')

def find_provider(provider, plist):
    for i in range(len(plist)):
        if plist[i]["id"] == provider["id"]:
            return i
    return None

def write_prompt_section(prompt_specs, prompts=None):
    prompts_section = ""
    for key in prompt_specs.keys():
        if prompts is None or re.search(prompts, key):
            prompts_section += f"""  - id: {key}
    label: {key}
    raw: exec:{python_path} -m promptfoo_tests.create_prompt exec_prompt --prompt {key}
"""
    return prompts_section

def write_provider_section(prompt_specs, prompts=None):
    provider_list = []
    for (key, value) in prompt_specs.items():
        if (prompts is None or re.search(prompts, key)) and value["config"].get("model", None) is not None:
            provider_record = {
                "id": f"openai:{value['config']['model']}",
            }
            idx = find_provider(provider_record, provider_list)
            if idx is None:
                provider_list.append(provider_record)
    provider_section = ""
    for record in provider_list:
        provider_section += f"""  - id: {record['id']}
    config:
      apiBaseUrl: "{{{{ env.LITELLM_BASE_URL }}}}"
      apiKey: "{{{{ env.LITELLM_API_KEY }}}}"
"""
    return provider_section

def default_fill(jsonSchema):
    if jsonSchema is None or jsonSchema == "null":
        return None
    elif jsonSchema == True:
        return True
    elif jsonSchema == False:
        return False
    elif jsonSchema.get("type", None) is None:
        return None
    elif jsonSchema["type"] == "string":
        return "default text"
    elif jsonSchema["type"] == "null":
        return None
    elif jsonSchema["type"] == "number" or jsonSchema["type"] == "integer":
        return 0
    elif jsonSchema["type"] == "boolean":
        return False
    elif jsonSchema["type"] == "array":
        return [default_fill(jsonSchema.get("items", {}))]
    elif jsonSchema["type"] == "object":
        if jsonSchema.get("additionalProperties", None) is None:
            return None
        else:
            return {"default_key": default_fill(jsonSchema["additionalProperties"])}
    else:
        return None

def write_individual_test(promptName, promptSpec, folderName):
    vars = promptSpec.get("vars", {})
    config = promptSpec.get("config", {}).get("modelConfig", {})
    vars_section = ""
    config_section= ""
    for (key, value) in vars.items():
        vars_section += f"      {key}: {json.dumps(default_fill(value))}\n"
    for (key, value) in config.items():
        config_section += f"      {key}: {json.dumps(value)}\n"
    base = f"""- description: 'Smoke test for {promptName}'
  vars:
{vars_section}  options:
{config_section}  prompts:
    - {promptName}

# Add more tests...
"""
    with open(f"./promptfoo_tests/{folderName}/test-{promptName}.yaml", "w") as f:
        f.write(base)

def write_tests_section(prompt_specs, prompts, name=None):
    # Create test_cases folder
    if name is None:
        folderName = "test_cases"
    else:
        folderName = "test_cases_" + name
    Path(f"./promptfoo_tests/{folderName}").mkdir(parents=True, exist_ok=True)
    tests_section = ""
    for (key, value) in prompt_specs.items():
        if prompts is None or re.search(prompts, key):
            tests_section += f"  - file://{folderName}/test-{key}.yaml\n"
            write_individual_test(key, value, folderName)
    return tests_section

def write_config(prompt_specs, prompts=None, name=None):
    base = f"""description: 'Generated config'

prompts:
{write_prompt_section(prompt_specs, prompts)}
providers:
{write_provider_section(prompt_specs, prompts)}
tests:
{write_tests_section(prompt_specs, prompts, name)}
"""
    if name is not None:
        filename = "./promptfoo_tests/promptfooconfig." + name + ".yaml"
    else:
        filename = "./promptfoo_tests/promptfooconfig.yaml"
    with open(filename, "w") as f:
        f.write(base)

def write_empty_config(name=None):
    base = """description: 'Empty config'

prompts:
# Add some prompts (https://www.promptfoo.dev/docs/configuration/prompts/)

providers:
# Add some providers (https://www.promptfoo.dev/docs/providers/)

tests:
# Add some tests (https://www.promptfoo.dev/docs/configuration/test-cases/)
"""
    if name is not None:
        filename = "./promptfoo_tests/promptfooconfig." + name + ".yaml"
    else:
        filename = "./promptfoo_tests/promptfooconfig.yaml"
    with open(filename, "w") as f:
        f.write(base)

if __name__ == '__main__':
    args = parser.parse_args()
    name = None
    if hasattr(args, "name") and args.name:
        if re.search("[^\\/:\"*?<>|\x00-\x1F]", args.name) is None or args.name[-1] == ".":
            raise Exception(f"Error: Invalid --name '{args.name}'.\nCharacters '\\', '/', ':', '\"', '*', '?', '<', '>', '|' and '\u0000-\u001F' are forbidden and your name cannot end with a dot.")
        else:
            name = args.name
    if args.command == "empty":
        write_empty_config(name)
    elif args.command == "all":
        prompt_specs = get_prompts()
        write_config(prompt_specs, name=name)
    elif args.command == "some":
        prompt_specs = get_prompts()
        write_config(prompt_specs, prompts=args.prompt, name=name)
    else:
        raise Exception(f"""Error: Invalid command '{args.command}'.
Allowed commands are 'empty', 'some' and 'all'.

python -m promptfoo_main empty
python -m promptfoo_main some --prompt <regex>
python -m promptfoo_main all
              """)