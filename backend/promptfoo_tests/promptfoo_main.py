import os
import json
from pathlib import Path
from promptfoo_tests.shared_state import get_prompts
import promptfoo_tests.file_registry

python_path = "C:/Users/clord/AppData/Local/Programs/Python/Python311/python.exe"

def find_provider(provider, plist):
    for i in range(len(plist)):
        if plist[i]["id"] == provider["id"]:
            return i
    return None

def merge(dict1, dict2):
    """
    add dict1 items to dict2 when the key is not in dict2
    """
    d = dict(dict1)
    for (key, value) in dict2.items():
        d[key] = value
    return d

def write_prompt_section(prompt_specs):
    prompts_section = ""
    for key in prompt_specs.keys():
        prompts_section += f"""  - id: {key}
    label: {key}
    raw: exec:{python_path} -m promptfoo_tests.create_prompt exec_prompt --prompt {key}
"""
    return prompts_section

def write_provider_section(prompt_specs):
    provider_list = []
    for (key, value) in prompt_specs.items():
        if value["config"].get("model", None) is not None:
            provider_record = {
                "id": f"openai:{value['config']['model']}",
                "config": value["config"].get("modelConfig", {}),
            }
            idx = find_provider(provider_record, provider_list)
            if idx is None:
                # provider_record["prompts"] = [key]
                provider_list.append(provider_record)
            else:
            #     provider_list[idx]["prompts"].append(key)
                provider_list[idx]["config"] = merge(provider_list[idx]["config"], provider_record["config"])
    provider_section = ""
    for record in provider_list:
        config = ""
        if record["config"] is not None:
            for (key, value) in record["config"].items():
                config+= f"\n      {key}: {{{{ {key} if {key} else {value} }}}}"
        provider_section += f"""  - id: {record['id']}
    config:
      apiBaseUrl: "{{{{ env.LITELLM_BASE_URL }}}}"
      apiKey: "{{{{ env.LITELLM_API_KEY }}}}"{config}
"""
    return provider_section

def write_provider_section_tmp():
    default_model = os.getenv("LITELLM_DEFAULT_MODEL", "").strip() or "claude-haiku-4-5"
    base = f"""  - id: openai:{default_model}
    config:
      apiBaseUrl: "{{{{ env.LITELLM_BASE_URL }}}}"
      apiKey: "{{{{ env.LITELLM_API_KEY }}}}"
"""
    return base

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

def write_individual_test(promptName, promptSpec):
    vars = promptSpec.get("vars", {})
    config = promptSpec.get("config", {}).get("modelConfig", {})
    vars_section = ""
    for (key, value) in vars.items():
        vars_section += f"      {key}: {json.dumps(default_fill(value))}\n"
    for (key, value) in config.items():
        vars_section += f"      {key}: {json.dumps(value)}\n"
    base = f"""- description: 'Smoke test for {promptName}'
  vars:
{vars_section}  prompts:
    - {promptName}

# Add more tests...
"""
    with open(f"./promptfoo_tests/test_cases/test-{promptName}.yaml", "w") as f:
        f.write(base)

def write_tests_section(prompt_specs):
    # Create test_cases folder
    Path("./promptfoo_tests/test_cases").mkdir(parents=True, exist_ok=True)
    tests_section = ""
    for (key, value) in prompt_specs.items():
        tests_section += f"  - file://test_cases/test-{key}.yaml\n"
        write_individual_test(key, value)
    return tests_section

def write_config(prompt_specs):
    base = f"""description: 'Generated config'

prompts:
{write_prompt_section(prompt_specs)}
providers:
{write_provider_section_tmp()}
tests:
{write_tests_section(prompt_specs)}
"""
    with open("./promptfoo_tests/promptfooconfig.yaml", "w") as f:
        f.write(base)

if __name__ == '__main__':
    prompt_specs = get_prompts()
    # print(f"[MAIN] prompt_registry: {prompt_specs}")
    write_config(prompt_specs)