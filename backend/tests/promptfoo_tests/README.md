# Promptfoo Tests

## Summary

1. [Overall Functionning](#overall-functionning)
2. [Register prompts with @register](#how-to-register-a-new-prompt-for-tests-)
3. [Generate config file](#generate-config-files)
4. [Generate config file - options](#generate-config-files---options)
5. [Manually add prompts](#how-to-manually-add-a-new-prompt-to-promptfooconfigyaml-)
6. [Edit config file](#edit-config-files)
7. [Run tests](#run-tests)

---

## Overall Functionning

We use node promptfoo library to perform prompt tests (cf https://www.promptfoo.dev/docs/getting-started/)

Additionnally to promptfoo, I created some python files to generate promptfoo config files skeleton simply by adding a `@register` decorator to your prompts.  

The steps are then:
1. Register your prompts
2. Generate config files
3. Manually edit config files, add more tests cases, etc.
4. Run tests

Organisation of `promptfoo_tests` folder :
 - `__init__.py`: The whole backend use modular programming. Files `__init__.py` allow to import python files as modules, with syntax with ".".
 - `create_prompt.py`: This file is the link between the `promptfooconfig.yaml` file and your registered prompt functions. You should not need to modify it.
 - `file_registry.py`: This file imports your desired files in order to fill the prompt registry.
 - `promptfoo_main.py`: This file runs `file_registry.py` and generates the promptfoo config files.
 - `README.md`: It's me :)
 - `shared_state.py`: This file contains the shared prompt_registry, as well as some getter and setter functions and the implementation of the `register` decorator. You should not need to modify it.

Generated Config Files (`promptfoo_config` folder) : 
- `promptfooconfig.yaml`: This is the main promptfoo config file, with 3 sections :
    - "prompts": the list of your prompts
    - "providers": the list of your providers
    - "tests": the list of your test cases
- `test_cases`: This folder contains one `*.yaml` file per prompt.
    - `test-<promptName>.yaml` : The list of test cases for \<promptName\>

#### Does promptfoo_tests folder works for other projects ?

Maybe if : 
- The project is in Python
- The project uses modular programming
- All AI calls pass through our internal GenAI stack

Else, the code needs to be translated.

---

## How to register a new prompt for tests ?

### 1. Isolate your prompt in a single function

It's recommended to specify the type of each argument if possible.  
Your prompt function must return either :
- a string (the "content" of the prompt),
- a message `{"role": ..., "content": ...}` (with role being either `user` or `system`),
- or a list of messages `[{"role": ..., "content": ...}, {"role": ..., "content": ...}, ...]`

❌ :

```python
async def ai_completion(last_question, current_step):
    prompt = f"""You are at this step in the form : {current_step}
Generate an answer to the last assistant question : {last_question}
    """
    answer = await llm_call(messages=[{"role": "user", "content": prompt}, model="claude-haiku-4-5", temperature=0.5])
    output = post_processing(answer)
    return output
```

✅ : 

```python
def ai_completion_prompt(last_question: str, current_step: int) -> str:
    return f"""You are at this step in the form : {current_step}
Generate an answer to the last assistant question : {last_question}
    """

async def ai_completion(last_question, current_step):
    prompt = ai_completion_prompt(last_question, current_step)
    answer = await llm_call(messages=[{"role": "user", "content": prompt}, model="claude-haiku-4-5", temperature=0.5])
    output = post_processing(answer)
    return output
```

*Note : don't name your arguments `cls` or `self` because they will be bypassed*  

*Note 2: your arguments must be json serializable (e.g. str or dict ✅ but callable ❌)*

### 2. Add `@register` decorator to your prompt function

You can add some model configuration as parameters to register, via `model` and `modelConfig`, in order to force provider configuration (optional).

```python
from tests.promptfoo_tests.shared_state import register

# ...

@register(model="claude-haiku-4-5", modelConfig={"temperature": 0.5})
def ai_completion_prompt(last_question: str, current_step: int) -> str:
    return f"""You are at this step in the form : {current_step}
Generate an answer to the last assistant question : {last_question}
    """
```

#### **Special Case : class method**

You can register class methods, but you have to add either `@classmethod` or `@staticmethod` to your method before the `@register` decorator :

```python
class MyClass:

    # ...

    @register()
    @classmethod
    def ai_completion_prompt(cls, last_question: str, current_step: int) -> str:
        return f"""You are at this step in the form : {current_step}
    Generate an answer to the last assistant question : {last_question}
        """
```

`@register` doesn't work with instance methods. If you need instance attributes in your method, you must add your prompt manually (cf [here](#how-to-manually-add-a-new-prompt-to-promptfooconfigyaml-)).

### 3. Import your file

In `file_registry.py`, import the file where your prompt functions are defined. 

Importing the file will execute all `@register` decorators in it.

If imported files themselves import other files, those file will be included in the registering.

`file_registry.py` :
``` py title="create_prompt.py"
import apps.quantum_readiness.maingraph
import core.graph
```

---

## Generate config files

*Note: For now, `promptfoo_main.py` is designed for powershell. If you use Linux, you'll need to edit the generated commands in the "prompts" section of `promptfooconfig.yaml`*

### 0. Prerequisite

Have Python installed and added to PATH.  
*Note: Pydantic is uncompatible with Python3.14, so I downgraded to Python3.11*

### 1. Install requirements

```bash
cd backend
pip install -r requirements.txt
```

### 2. Scpecify Python Path in `promptfoo_main.py`

I don't know why but promptfoo cannot find python even if it's added to PATH, so you need to specify the exact path of python executable :

`promptfoo_main.py` :
```python
python_path = "C:/Users/clord/AppData/Local/Programs/Python/Python311/python.exe"
```

### 3. Run `promptfoo_main.py`

Make sure you execute the following command in `backend` folder :

```bash
python -m tests.promptfoo_tests.promptfoo_main all
```

*Note: register decorators are executed when promptfoo executes create_prompt.py, so if you edited a prompt after a generation, you don't need to regenerate all files (you simply need to updates the associated test file if you modified arguments or model config).*

---

## Generate config files - Options

### Generate empty config file

```bash
python -m tests.promptfoo_tests.promptfoo_main empty
```

The output will be :

`promptfooconfig.yaml`:
```
description: 'Empty config'

prompts:
# Add some prompts (https://www.promptfoo.dev/docs/configuration/prompts/)

providers:
# Add some providers (https://www.promptfoo.dev/docs/providers/)

tests:
# Add some tests (https://www.promptfoo.dev/docs/configuration/test-cases/)
```

### Generate config only for some prompts

```bash
python -m tests.promptfoo_tests.promptfoo_main some --prompt <regex>
```

where `<regex>` is a python regex : https://www.w3schools.com/python/python_regex.asp#matchobject

This command will only take into account prompts whose name matches with the regex.

**What is the name of a prompt ?**

Prompts are generally identified by the [qualname](https://peps.python.org/pep-3155/) of the registered function.  
For instance, the function _prompt_ai_completion in the class QuantumDataCollector will have the ID "QuantumDataCollector._prompt_ai_completion"  

If 2 functions have the same qualname, their ID will be `<module>.<qualname>`.

If a function is a lambda, their ID will be `<qualname><random UUID>`.

**Examples :**

1. Select class1.func1 and class1.func2 : 
```bash
python -m tests.promptfoo_tests.promptfoo_main some --prompt "class1\.func1|class1\.func2"
```

2. Select all prompts in class1 :
```bash
python -m tests.promptfoo_tests.promptfoo_main some --prompt "class1\."
```

### Specify a name for config files

Use this option if you want to generate several files without overwritting the previous ones.

```bash
python -m tests.promptfoo_tests.promptfoo_main all --name <valid-file-name>
```

Then, `promptfooconfig.yaml` will be named `promptfooconfig.<name>.yaml` instead, and `test_cases` folder will become `test_cases_<name>`

---

## How to manually add a new prompt to `promptfooconfig.yaml` ?

### 1. Isolate your prompt in a single function

❌ :

```python
async def ai_completion(last_question, current_step):
    prompt = f"""You are at this step in the form : {current_step}
Generate an answer to the last assistant question : {last_question}
    """
    answer = await llm_call(messages=[{"role": "user", "content": prompt}, model="claude-haiku-4-5", temperature=0.5])
    output = post_processing(answer)
    return output
```

✅ : 

```python
def ai_completion_prompt(last_question: str, current_step: int) -> str:
    return f"""You are at this step in the form : {current_step}
Generate an answer to the last assistant question : {last_question}
    """

async def ai_completion(last_question, current_step):
    prompt = ai_completion_prompt(last_question, current_step)
    answer = await llm_call(messages=[{"role": "user", "content": prompt}, model="claude-haiku-4-5", temperature=0.5])
    output = post_processing(answer)
    return output
```

*Note: your arguments must be json serializable (e.g. str or dict ✅ but callable ❌)*

### 2. Write a wrapper in any file:

```python
def ai_completion_prompt_wrapper(context) -> str:
    vars = context['vars']
    last_question = vars.get("last_question", "")
    current_step = vars.get("current_step", 0)
    return ai_completion(last_question, current_step)
```

**Rules:**
- Your wrapper function must take one argument `context`, that contains test config (cf https://www.promptfoo.dev/docs/configuration/prompts/#python-functions).
- Your wrapper function must return either :
    - a string (the "content" of the prompt),
    - a message `{"role": ..., "content": ...}` (with role being either `user` or `system`),
    - or a list of messages `[{"role": ..., "content": ...}, {"role": ..., "content": ...}, ...]`

### 3. Edit prompts in `promptfooconfig.yaml`

`promptfooconfig.yaml`:
```
prompts:
  - file://<path-to-your-wrapper-file>:ai_completion_prompt_wrapper
```

### 4. Edit providers in `promptfooconfig.yaml` if needed

cf https://www.promptfoo.dev/docs/providers/

### 5. Edit tests in `promptfooconfig.yaml`

cf https://www.promptfoo.dev/docs/configuration/test-cases/

---

## Edit config files

### 1. Prompts section

If you want to compare several versions of a prompt, you can add those versions inside the "prompts" section of your `promptfooconfig.yaml` :

```
prompts:

  - label: QuantumAnalyzerTool._prompt_score_branch
    raw: exec:C:/Python/Python311/python.exe -m tests.promptfoo_tests.create_prompt exec_prompt --prompt QuantumAnalyzerTool._prompt_score_branch

  - label: QuantumAnalyzerTool._prompt_narrative
    raw: exec:C:/Python/Python311/python.exe -m tests.promptfoo_tests.create_prompt exec_prompt --prompt QuantumAnalyzerTool._prompt_narrative

  - ...

  - label: QuantumAnalyzerTool._prompt_score_branch_variation1
    raw: 'I am a slightly different version of the score_branch prompt. Here, I include a test variable : {{some_variable}}'
```

In order to not surcharge your `promptfooconfig.yaml`, you can alternatively write all your variations inside a .txt file and include the file inside the "prompts" section. Separate prompt varations with "---".

`prompt_score_branch.txt`: 
```
I am a variation 1 of the score_branch prompt. Here, I include a test variable : {{some_variable}}
---
I am a variation 2 of the score_branch prompt. Here, I include a test variable : {{some_variable}}
---
I am a variation 3 of the score_branch prompt. Here, I include a test variable : {{some_variable}}
```

`promptfooconfig.yaml`:
```
prompts:

  - label: QuantumAnalyzerTool._prompt_score_branch
    raw: exec:C:/Python/Python311/python.exe -m tests.promptfoo_tests.create_prompt exec_prompt --prompt QuantumAnalyzerTool._prompt_score_branch

  - label: QuantumAnalyzerTool._prompt_narrative
    raw: exec:C:/Python/Python311/python.exe -m tests.promptfoo_tests.create_prompt exec_prompt --prompt QuantumAnalyzerTool._prompt_narrative

  - ...

  - id: file://<path-to-prompt_score_branch.txt>
    label: QuantumAnalyzerTool._prompt_score_branch_variations
```

*Note: labels of your prompt variations should be an extension of the label of your original prompt, so that test .yaml is still associated to variations.*

More informations on the "prompts" section here : https://www.promptfoo.dev/docs/configuration/prompts/

### 2. Providers section

cf https://www.promptfoo.dev/docs/providers/

### 3. Tests section

cf https://www.promptfoo.dev/docs/configuration/test-cases/

---

## Run tests

### 0. Prerequisites

- Having Node.js installed ([download page](https://nodejs.org/en/download))
- Have API key for our internal genAI stack ([guide Litellm](https://github.com/Center-for-Hybrid-Intelligence/LiteLLM-QuantumChatbots/blob/main/README.md))

### 1. Run tests

Navigate to `backend` folder and run :

```bash
npx promptfoo@latest eval -c ./tests/promptfoo_config/promptfooconfig.yaml --env-file .env
```

Don't forget to update the filename `promptfooconfig.yaml` with `promptfooconfig.<name>.yaml` if needed.

### 2. View results

```bash
npx promptfoo@latest view
```

Type "y" when the terminal asks you to.