import asyncio
from pprint import pprint

from app.tools.product import create_product_tools
from app.tools.dependencies import product_service_context


async def main():
    tools = create_product_tools(product_service_context)

    tools_by_name = {tool.name: tool for tool in tools}
    search_tool = tools_by_name["search_products"]

    result = await search_tool.ainvoke({
        "query": "keyboard",
    })

    print("\n--- TOOL OUTPUT TYPE ---")
    print(type(result))

    print("\n--- TOOL OUTPUT VALUE ---")
    pprint(result, width=100, sort_dicts=False)


if __name__ == "__main__":
    asyncio.run(main())