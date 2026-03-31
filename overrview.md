I will have an ochestrator and worker agents. These agetns will be reAct agents from langcahin which will use the different tools i assign to them.

This will be a full stack

backend - fastapi for restful api, langgraph / langchain, some api connecting to the different Saas like gmail calender etc

front end- react-vite

# Flow

- I will have some human in the loop functions as well yah
- I will likely create some standard flow with some agent involved.

# Features?

- Simple Ones:

1. Help to set up meeting with googlemeets?
2. Help to draft email to someone
3. Help to search for information online and summarize it

- Complex Ones:

1. Help order food for you?
2. Help book a seat at NLB (COOL LOL)
3. Help to book restaurants?
4. Buy gym pass to activeSG?

## How to first?

- For langgraph, you would need define your state. This state will be passed to your graph.
- Any changes to this state will be reflected in the next node that is being called.

- In the graph, it will first reach ochestrator which has access to heavily restricted tools
- These tools are like functions pointing or routing nodes pointing to differnet agents nodes.
- Then the worker agent will run
- It will then route back to ochestrator agent..
- Finishes with end node hor...
