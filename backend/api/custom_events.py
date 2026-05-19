'''
In this file, you can define how to handle your custom events before the streaming

Your custom events must have the following arguments : 
    - name : the event name : used to select the appropriate function
    - data : any data relative to the event

every event handler must return
    - a type (str)
    - a payload (Dict)
    - a meta (Dict)
'''

from typing import Dict

# Handle events that occur during the graph execution
async def eventSelector(name: str, data: Dict, meta: Dict=None, eventLogger=None):
    if name == "tool_start" or name == "tool_progress" or name == "tool_complete":
        name, data, meta = await tool_handler(name, data, meta, eventLogger)
    # Add your custom event here if needed
    else: # Default
        name, data, meta = await default_handler(name, data, meta, eventLogger)
    return name, data, meta


async def default_handler(name, data, meta, eventLogger):
    print(f"[SSE_STREAM] Event: {name}")
    await eventLogger(
        name,
        payload=data,
    )
    return name, data, meta

async def tool_handler(name, data, meta, eventLogger):
    print(f"[SSE_STREAM] {name} : {data.get('tool_name')}")
    await eventLogger(
        name,
        tool_name=data.get("tool_name"),
        payload=data,
    )
    return name, data, meta