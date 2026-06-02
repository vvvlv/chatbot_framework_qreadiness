# Tests for field transition in data_collector

This is a first draft of a unit test for a single prompt.

## Prerequisite

1. Have a Litellm key on our internal OpenWebUI

One virtual key per chatbot, so usage and costs can be tracked per bot.

Ask Alexis Vrielynck (or any Litellm admin) for a personalized key. If Alexis Vrielynck is not available, you can find credentials in the VM:

URL: https://litellm-quantumchatbots.hybridintelligence.eu/ui/
Username: admin
Password: in the .env of the project

2. In your .env (of the backend), make sure the following lines are filled

```env
# LiteLLM proxy
LITELLM_BASE_URL=http://litellm-quantumchatbots:4000     # production, on the VM
# LITELLM_BASE_URL=https://litellm-quantumchatbots.hybridintelligence.eu  # local dev
LITELLM_API_KEY=sk-<the-virtual-key-generated-in-step-1>
```

4. Have Node.js locally installed on your computer

Install from here : https://nodejs.org/en/download 

## Config

1. Edit Provider's list

To add a model in the test, add the following record in the section `providers` of `promptfooconfig.yaml`

```
  - id: <provider>:<model_name>
    config:
      apiBaseUrl: "{{ env.LITELLM_BASE_URL }}"
      apiKey: "{{ env.LITELLM_API_KEY }}"
      <other params if needed>
```

Make sure your model is in the model list of our internal OpenWebUI : https://litellm-quantumchatbots.hybridintelligence.eu/ui/?page=models
If not, add the model in the list (you'll need a specific API key for the model).

2. Add more test cases

Add as much test cases as you want in the section `tests` of `promptfooconfig.yaml`

## Start tests

1. Go to the directory containing your promptfooconfig.yaml

```bash
cd ./backend/single_promptfoo_tests
```

2. Run the evaluation:

```bash
npx promptfoo@latest eval --env-file ../.env
```

3. View results in web UI

```bash
npx promptfoo@latest view
```

## Promptfoo's doc

https://www.promptfoo.dev/docs/getting-started/ 
