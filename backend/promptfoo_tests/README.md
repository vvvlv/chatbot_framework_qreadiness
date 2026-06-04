# Promptfoo Tests

## Summary

1. [Overall Functionning](#overall-functionning)
2. [Register prompts with @register](#how-to-register-a-new-prompt-for-tests-)
3. [Generate config file](#generate-config-files)
4. Fill Config file
5. [Manually add prompts](#how-to-manually-add-a-new-prompt-to-promptfooconfigyaml-)
6. [Run tests](#run-tests)

---

## Overall Functionning

We use node promptfoo library to perform prompt tests (cf https://www.promptfoo.dev/docs/getting-started/)

Additionnally to promptfoo, I created some python files to generate promptfoo config files skeleton simply by adding a `@register` decorator to your prompts.  

The steps are then:
1. Registering your prompts
2. Generate the config files
3. Manually edit config files, add more tests cases, etc.
4. Run tests

Organisation of `promptfoo_tests` folder :
 - `__init__.py`: The whole backend use modular programming. Files `__init__.py` allow to import python files as modules, with syntax with ".".
 - `create_prompt.py`: This file is the link between the `promptfooconfig.yaml` file and your registered prompt functions. You should not need to modify it.
 - `file_registry.py`: This file imports your desired files in order to fill the prompt registry.
 - `promptfoo_main.py`: This file runs `file_registry.py` and generates the promptfoo config files.
 - `provider.py`: This file is the link between the `promptfooconfig.yaml` file and registered providers/models configs. It's not implemented yet.
 - `README.md`: It's me :)
 - `shared_state.py`: This file contains the shared prompt_registry, as well as some getter and setter functions and the implementation of the `register` decorator. You should not need to modify it.

Generated Config Files : 
- `promptfooconfig.yaml`: This is the main promptfoo config file, with 3 sections :
    - "prompts": the list of your prompts
    - "providers": the list of your providers
    - "tests": the list of your test cases
- `test_cases`: This folder contains one `*.yaml` file per prompt.
    - `test-<promptName>.yaml` : The list of test cases for \<promptName\>

#### Does this approach works for other projects ?

Maybe if : 
- The project is in Python
- The project uses modular programming
- All AI calls pass through our internal GenAI stack

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
from promptfoo_tests.shared_state import register

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

*Note: `promptfoo_main.py` is designed for powershell. For now it doesn't work on linux.*

### 0. Prerequisite

Having Python installed and added to PATH.  
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
python -m promptfoo_tests.promptfoo_main
```

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

## Run tests

### 0. Prerequisites

Having Node.js installed

### 1. Run tests

Navigate to `backend` folder and run :

```bash
npx promptfoo@latest eval -c ./promptfoo_tests/promptfooconfig.yaml --env-file .env
```

### 2. View results

```bash
npx promptfoo@latest view
```

Type "y" when the terminal asks you to.