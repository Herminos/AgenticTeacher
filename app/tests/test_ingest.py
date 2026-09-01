from pathlib import Path

from ingest import build_rows


def test_ingest_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "chapter.md"
    source.write_text("## 极限\n\n洛必达法则用于 0/0 型极限。", encoding="utf-8")
    first = build_rows(tmp_path, hyde_count=2)
    second = build_rows(tmp_path, hyde_count=2)
    assert first == second
    assert first[0]["metadata"]["chunk_id"] == second[0]["metadata"]["chunk_id"]
