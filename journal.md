# 1/4/26

I will have an ochestrator and worker agents. These agetns will be reAct agents from langcahin which will use the different tools i assign to them.

This will be a full stack

backend - fastapi for restful api, langgraph / langchain, some api connecting to the different Saas like gmail calender etc

front end- react-vite

# Flow

- I will have some human in the loop functions as well yah
- I will likely create some standard flow with some agent involved.
- All the nodes must return the states yah, whihc contains teh config and state defined...

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

# in each agent file

- You have your tools
- init of the create_agent
- Worker node which is placed in the graph flow

## Done?

- I think the calander agent is done for now
- Added delete, conflict check, create, get events

## What is the ochestrator tiny

- We will have tools to delegate tasks to the correct agent yah

## To end node

orchestrator_node runs
↓
Last message is AIMessage? (Python check, instant) or just a dict returned
├── YES → next_agent = "end" (NO LLM call)
└── NO → call \_classify_intent(messages)
↓
LLM invoked once
Returns "calendar_worker" / "email_worker" / "end"
↓
next_agent = LLM decision

        ↓

orchestrator_router reads next_agent from state
├── "calendar_worker" → route to calendar_worker node
├── "email_worker" → route to email_worker node
└── anything else → "**end**"

- Note that create_agent will return a dict with the key "messages" which contains the AI response AIMessage automatically yah

# 2/4/26

- How a single turn works
  User types: "Read my emails" -> This triggers graph.invoke() (or stream).
  Orchestrator wakes up, sees the human message, routes to email_worker.
  Email Agent wakes up, calls the read_email tool, generates an AIMessage with the summary, and returns it.
  Graph Edge from email_worker points back to orchestrator, so the orchestrator wakes up again.
  Orchestrator sees the last message is an AIMessage. It says "Okay, the worker did its job. I have nothing left to do." -> It routes to END.
  When it hits END, the graph.invoke() function call finishes, and your API returns the response to the frontend. The system then waits patiently.

So will route to worker, at the very end, after calling all the ToolMessage, if it finsihses its task i will return an AIMessage. This will signal to start and retrun to orchestrator then to end.

- When you enter a reply again it will start a new thread?
