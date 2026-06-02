# Promptfoo Tests

## Overall Functionning

TODO

## How to register a new prompt for tests ?

### 1. Isolate your prompt in a single function

It's recommended to specify the type of each argument if possible.  
Your prompt function must return either :
- a string,
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

You can add any model configuration as parameters to register

```python
from promptfoo_tests.shared_state import register

# ...

@register(temperature=0.5)
def ai_completion_prompt(last_question: str, current_step: int) -> str:
    return f"""You are at this step in the form : {current_step}
Generate an answer to the last assistant question : {last_question}
    """
```

### 3. Import your file

In `create_prompt.py`, import the file where your prompt functions are defined. If you centralized your prompt functions inside a single class or function, you can simply import it, in order to not load the whole file.  

Importing the code section will execute all `@register` decorators in it.

If imported files themselves import other files, those file will be included in the registering

`create_prompt.py` :
``` py title="create_prompt.py"
import apps.quantum_readiness.maingraph
import core.graph
```

**Note (problem to solve): Whenever you make a `print` in your imported files, if this `print` is executed during the file import, you must add the argument `file=sys.stderr` in it**

## Run tests

**Prerequisite :** Having Pyhton installed and added to PATH

### 1. Install requirements

```bash
cd backend
pip install -r requirements.txt
```

### 2. Run `promptfoo_main.js`

...