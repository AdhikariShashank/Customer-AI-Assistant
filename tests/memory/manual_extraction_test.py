
import asyncio

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.memory.extractor import MemoryExtractor


load_dotenv()


async def main():
    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
    )

    extractor = MemoryExtractor(llm)

    messages = [
        "I prefer Samsung phones and my budget is INR 30000.",
        "My previous order arrived late and I requested a refund.",
        "What is the price of the iPhone 16?",
        "Forget my preference for Samsung phones.",
    ]

    for message in messages:
        print(f"\nCUSTOMER: {message}")

        result = await extractor.extract(
            customer_message=message
        )

        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
