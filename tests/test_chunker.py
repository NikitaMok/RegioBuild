from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import Section


def test_short_section_becomes_single_chunk() -> None:
    sections = [Section(number="1", text="Короткий текст пункта норматива.")]
    chunks = chunk_sections(sections, region_code="moscow_oblast", max_chars=800, overlap=100)

    assert len(chunks) == 1
    assert chunks[0].region_code == "moscow_oblast"
    assert chunks[0].section_number == "1"


def test_long_section_is_split_with_overlap() -> None:
    long_text = " ".join(["слово"] * 300)  # ~1800 символов
    sections = [Section(number="2", text=long_text)]
    chunks = chunk_sections(sections, region_code="krasnodar_krai", max_chars=500, overlap=50)

    assert len(chunks) > 1
    assert all(c.section_number == "2" for c in chunks)
    assert all(c.char_count <= 500 + 1 for c in chunks)  # +1 запас на границу слова


def test_chunk_sections_preserves_section_order() -> None:
    sections = [
        Section(number="1", text="Первый пункт."),
        Section(number="2", text="Второй пункт."),
    ]
    chunks = chunk_sections(sections, region_code="moscow_oblast")

    assert [c.section_number for c in chunks] == ["1", "2"]
