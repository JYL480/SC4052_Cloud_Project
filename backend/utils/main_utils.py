"""
I will have to wrap with langchain wit this. Langchain-ollama....

"""

from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, HumanMessage

END_POINT = "http://localhost:11434"

# Single client instance pointing at your Ollama server
llm_model = ChatOllama(
    model="qwen3:latest",
    base_url="http://localhost:11434"
)

def llm_generate_response(
    prompt: str,
    model: str = "qwen3:latest",
    system: str | None = None,
) -> AIMessage:
    """Send a prompt to a local Ollama model and return the response text.

    Args:
        prompt:  The user message / query.
        model:   Ollama model tag to use (must be pulled locally first).
        system:  Optional system message to prepend.

    Returns:
        The model's reply as a plain string.
    """
    messages: list[dict] = []

    if system:
        messages.append({"role": "system", "content": system})

    messages.append({"role": "user", "content": prompt})

    response = llm_model.invoke(messages)

    return AIMessage(content=response.content)
    
    





if __name__ == "__main__":
    # Quick smoke-test — make sure Ollama is running locally first.
    reply = llm_generate_response("What is 2 + 2?")
    print(reply)

