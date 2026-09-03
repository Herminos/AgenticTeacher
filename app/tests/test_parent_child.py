import pytest

from app.services.index_service import _child_chunks, _light_rag_child_ids, _parent_blocks
from app.services.lightrag_service import LightRAGService


def test_markdown_sections_become_parent_blocks_without_empty_first_block():
    parents = _parent_blocks("# 第一节\n\n定义\n\n# 第二节\n\n定理")
    assert len(parents) == 2
    assert parents[0].startswith("# 第一节")
    assert parents[1].startswith("# 第二节")


def test_child_chunks_keep_parent_mapping():
    parents = ["# A\n\n" + "甲" * 20, "# B\n\n乙"]
    children, mapping = _child_chunks(parents, 8)
    assert children
    # Hashes can collide for identical child text; the persisted child_id
    # mapping is authoritative for that case.
    assert len(mapping) <= len(children)
    assert {mapping[next(iter(mapping))]} <= {"parent_1", "parent_2"}


def test_child_id_mapping_uses_lightrag_document_scoped_ids():
    from lightrag.utils_pipeline import make_custom_chunk_id

    children, parents = _child_chunks(["# 第一节\n\n定义", "# 第二节\n\n公式"], 512)
    mapping = _light_rag_child_ids("doc-test", children, parents)
    assert mapping[make_custom_chunk_id("doc-test", children[0])] == "parent_1"
    assert mapping[make_custom_chunk_id("doc-test", children[1])] == "parent_2"


@pytest.mark.asyncio
async def test_embedding_and_reranker_fail_closed_when_disabled(monkeypatch):
    service = LightRAGService()
    monkeypatch.setattr(service.settings, "hf_enable_local_models", False)
    monkeypatch.setattr(service.settings, "hf_enable_reranker", False)
    with pytest.raises(RuntimeError, match="embedding is disabled"):
        await service._embedding(["文本"])
    with pytest.raises(RuntimeError, match="reranker is disabled"):
        await service._rerank("问题", ["文本"])


def test_parent_lookup_prefers_stable_child_id_and_falls_back_to_normalized_text():
    record = {
        "parent_blocks": [{"parent_id": "parent_1", "text": "# 节\n\n含有公式 $$E=mc^2$$"}],
        "child_ids": {"child-1": "parent_1"},
        "child_parents": {},
    }
    text, parent_id = LightRAGService._parent_for_child(record, "不同空白", "child-1")
    assert parent_id == "parent_1"
    assert "E=mc^2" in text

    text, parent_id = LightRAGService._parent_for_child(record, "含有公式   $$E=mc^2$$")
    assert parent_id == "parent_1"
    assert text


@pytest.mark.asyncio
async def test_retrieval_selects_four_children_before_parent_dedup(monkeypatch):
    import app.services.rag_registry as registry_module

    chunks = [
        {"chunk_id": f"child-{index}", "content": f"child text {index}", "file_path": "unknown_source"}
        for index in range(5)
    ]

    class TextChunks:
        async def get_by_ids(self, ids):
            return [{"_id": item, "full_doc_id": "doc"} for item in ids]

    class Rag:
        text_chunks = TextChunks()

        async def aquery_data(self, *_):
            return {"status": "success", "data": {"chunks": chunks}, "metadata": {}}

    parents = [{"parent_id": f"parent-{index}", "text": f"parent text {index}"} for index in range(5)]
    record = {"source_id": "doc", "filename": "book.md", "parent_blocks": parents, "child_ids": {f"child-{index}": f"parent-{index}" for index in range(5)}}

    class Registry:
        def runtime_settings(self):
            return {"reranker_top_k": 4}

        def list_files(self, _subject):
            return [record]

    service = LightRAGService()
    monkeypatch.setattr(service, "_create", lambda *_: _async_value(Rag()))
    monkeypatch.setattr(registry_module, "get_rag_registry", lambda: Registry())
    documents, _ = await service.retrieve("query", "physics", 16)
    assert [item["metadata"]["child_id"] for item in documents] == ["child-0", "child-1", "child-2", "child-3"]
    assert all(item["metadata"]["parent_id"] != "parent-4" for item in documents)


async def _async_value(value):
    return value
