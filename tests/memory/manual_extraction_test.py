
import asyncio

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.memory.extractor import MemoryExtractor


import logging

logger = logging.getLogger(__name__)

load_dotenv()


async def test_live_forget(extractor):
    existing_memories = [
        {
            "category": "preference",
            "key": "preferred_phone_brand",
            "value": {"brand": "Samsung"},
        },
        {
            "category": "constraint",
            "key": "phone_budget",
            "value": {
                "amount": 30000,
                "currency": "INR",
            },
        },
    ]

    logger.info(
        "memory.live_forget_test_started existing_memory_count=%d",
        len(existing_memories),
    )

    result = await extractor.extract(
        customer_message="Forget my preference for Samsung phones.",
        existing_memories=existing_memories,
    )

    print(result.model_dump_json(indent=2))

    logger.info(
        "memory.live_forget_test_completed operations=%d",
        len(result.semantic_operations),
    )

    return result


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
        "My phone budget has increased to INR 40000.",
    ]

    for message in messages:
        print(f"\nCUSTOMER: {message}")

        result = await extractor.extract(
            customer_message=message
        )

        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
