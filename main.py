import asyncio

from dotenv import load_dotenv
from langchain.agents import create_agent

from file_system_mcp import file_system_mcp_tool
from prompt import SYSTEM_PROMPT

from langchain_community.tools import DuckDuckGoSearchRun


async def main():
    search = DuckDuckGoSearchRun()
    load_dotenv()

    file_system_tool = await file_system_mcp_tool().get_tools()

    agent = create_agent(
        model="google_genai:gemini-3.5-flash",
        tools=[search, *file_system_tool],
        system_prompt=SYSTEM_PROMPT
    )

    while True:
        human_question = input("Please enter your question: ")
        if human_question == "exit":
            break
        response = agent.invoke({"messages": [{"role": "user", "content": human_question}]})
        print(response["messages"][-1].content[0]["text"])

if __name__=="__main__":
    asyncio.run(main())