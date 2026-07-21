from app.ingestion.parser import extract_text_from_html, split_into_sections


def test_extract_text_from_html_strips_scripts_and_tags() -> None:
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <script>console.log('noise')</script>
        <nav>Меню сайта</nav>
        <main>
          <p>1. Общие положения нормативов.</p>
          <p>1.1. Расчетные показатели плотности застройки.</p>
        </main>
      </body>
    </html>
    """
    text = extract_text_from_html(html)
    assert "console.log" not in text
    assert "Меню сайта" not in text
    assert "Общие положения нормативов." in text


def test_split_into_sections_groups_by_numbering() -> None:
    text = (
        "1. Общие положения нормативов, применимые ко всем видам застройки региона.\n"
        "Продолжение первого пункта на следующей строке документа.\n"
        "2. Расчетные показатели плотности застройки и требования к параметрам объектов.\n"
    )
    sections = split_into_sections(text, min_section_chars=10)

    assert len(sections) == 2
    assert sections[0].number == "1"
    assert "Продолжение первого пункта" in sections[0].text
    assert sections[1].number == "2"


def test_split_into_sections_handles_nested_numbering() -> None:
    text = "4.5.2 Показатель обеспеченности объектами социальной инфраструктуры в населенных пунктах."
    sections = split_into_sections(text, min_section_chars=10)

    assert len(sections) == 1
    assert sections[0].number == "4.5.2"


def test_split_into_sections_does_not_treat_table_columns_as_points() -> None:
    text = (
        "5.5.153 Требуемое количество машино-мест определяется по таблице 108.\n"
        "Таблица 108 Рекреационные территории | Расчетная единица | количество машино-мест\n"
        "1 | 2 | 3 Здания и сооружения | Здания и сооружения\n"
        "Станции технического обслуживания, автомойки | 1 бокс | 1\n"
        "300 | 1,2\n"
        "5.5.154 Автостоянки в пределах городских улиц проектируются закрытыми.\n"
    )
    sections = split_into_sections(text, min_section_chars=10)
    numbers = [section.number for section in sections]
    assert "5.5.153" in numbers
    assert "5.5.154" in numbers
    assert "1" not in numbers
    assert "300" not in numbers
    table_sections = [s for s in sections if s.number and s.number.startswith("табл.")]
    assert table_sections
    assert any("автомойки" in (s.text or "") for s in table_sections)
