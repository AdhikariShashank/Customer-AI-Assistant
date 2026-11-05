from types import SimpleNamespace

from app.memory.context_builder import MemoryContextBuilder
from app.memory.retriever import RetrievedMemories


def test_memory_context_builder_formats_memories():

    memories = RetrievedMemories(
        semantic=[
            SimpleNamespace(
                category="preference",
                key="preferred_phone_brand",
                value={"brand": "Samsung"},
                is_active=True,
            ),
            SimpleNamespace(
                category="constraint",
                key="phone_budget",
                value={"amount": 30000, "currency": "INR"},
                is_active=True,
            ),
        ],
        episodic=[
            SimpleNamespace(
                event_type="delivery_issue",
                description="Order 101 was delayed",
            ),
        ],
    )

    builder = MemoryContextBuilder(max_chars=4000)

    context = builder.build(memories)

    assert "preferred_phone_brand" in context
    assert "Samsung" in context
    assert "phone_budget" in context
    assert "delivery_issue" in context
    assert "Order 101 was delayed" in context

    assert "untrusted data" in context


def test_memory_context_builder_excludes_inactive_memories():

    memories = RetrievedMemories(
        semantic=[
            SimpleNamespace(
                category="preference",
                key="old_phone_brand",
                value={"brand": "Apple"},
                is_active=False,
            ),
        ],
    )

    builder = MemoryContextBuilder()

    context = builder.build(memories)

    assert "old_phone_brand" not in context


def test_memory_context_builder_respects_size_limit():

    memories = RetrievedMemories(
        semantic=[
            SimpleNamespace(
                category="preference",
                key="long_preference",
                value={"description": "A" * 5000},
                is_active=True,
            ),
        ],
    )

    builder = MemoryContextBuilder(max_chars=500)

    context = builder.build(memories)

    assert len(context) <= 500
    assert "A" * 5000 not in context


def test_memory_context_builder_empty_memories():

    builder = MemoryContextBuilder()

    context = builder.build(
        RetrievedMemories()
    )

    assert "Customer memory context" in context
    assert "Semantic memories:" not in context
    assert "Recent episodes:" not in context