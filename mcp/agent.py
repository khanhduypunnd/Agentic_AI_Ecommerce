from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq

from dotenv import load_dotenv

load_dotenv()

import asyncio


async def main():
    client = MultiServerMCPClient(
        {
            # "math":{
            #     "command":"python",
            #     "args":["first_server.py"], ## Ensure correct absolute path
            #     "transport":"stdio",
            # },
            "weather": {
                "url": "http://localhost:8000/mcp",  # Ensure server is running here
                "transport": "streamable_http",
            }
        }
    )

    import os

    os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

    tools = await client.get_tools()
    model = ChatGroq(model="qwen/qwen3-32b")
    agent = create_react_agent(model, tools)

    # math_response = await agent.ainvoke(
    #     {"messages": [{"role": "user", "content": "what's (3 + 5) x 12?"}]}
    # )

    # print("Math response:", math_response['messages'][-1].content)

    weather_response = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "system",
                    "content": 'Bạn là một trợ lý bán nước hoa. Bạn có thể truy vấn thông tin về các sản phẩm nước hoa và hỗ trợ khách hàng trong quá trình chọn mua.\n\
Bạn được cấp quyền sử dụng hai công cụ:\n\
- `tavily_web_search`: chỉ được dùng khi cần tìm kiếm thông tin trên web liên quan đến mua bán, đánh giá, hoặc xu hướng thị trường nước hoa.\n\
- `get_product_variations`: dùng để truy vấn thông tin chi tiết về sản phẩm nước hoa như mùi hương, giá, hình ảnh, liên kết mua hàng, stock,...\n\
Hãy xưng hô là "em" và gọi người dùng là "anh/chị" tùy theo ngữ cảnh.',
                },
                {
                    "role": "user",
                    "content": 'tìm cho tôi thông tin sản phẩm "Lancôme Tresor La Nuit EDP" và bản tester còn hàng không ? /no_think',
                },
            ]
        }
    )
    print("Response:", weather_response["messages"][-1].content)


asyncio.run(main())
