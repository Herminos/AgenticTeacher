from pathlib import Path

from ingest import build_rows


def test_ingest_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "chapter.md"
    source.write_text("## 极限\n\n洛必达法则用于 0/0 型极限。", encoding="utf-8")
    first = build_rows(tmp_path, hyde_count=2)
    second = build_rows(tmp_path, hyde_count=2)
    assert first == second
    assert first[0]["metadata"]["chunk_id"] == second[0]["metadata"]["chunk_id"]


def test_ingest_source_id_is_stable_across_upload_directories(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    for directory in (first_dir, second_dir):
        (directory / "chapter.md").write_text("拉普拉斯变换的定义。", encoding="utf-8")
    first = build_rows(first_dir)
    second = build_rows(second_dir)
    assert first[0]["metadata"]["source_id"] == second[0]["metadata"]["source_id"]
    assert first[0]["metadata"]["chunk_id"] == second[0]["metadata"]["chunk_id"]
