from parsing_benchmark import html_table_rows, marker_page_texts, marker_tables

TABLE = ("<table><tbody><tr><th>Κονδύλι</th><th>31.12.2024</th><th>31.12.2023</th></tr>"
         "<tr><td>Κύκλος<br/>εργασιών</td><td>1.146.865,95</td><td>900,00</td></tr>"
         "<tr><td colspan=\"2\">Σύνολο</td><td>5 &amp; 6</td></tr></tbody></table>")

def page(n, children):
    return dict(id=f"/page/{n}/Page/0", block_type="Page", html="", children=children)

DOC = dict(block_type="Document", children=[
    page(0, [dict(id="/page/0/Text/1", block_type="Text", html="<p>Ισολογισμός &amp; αποτελέσματα</p>", children=None)]),
    page(1, [dict(id="/page/1/TableGroup/2", block_type="TableGroup", html="", children=[
        dict(id="/page/1/Table/3", block_type="Table", html=TABLE, children=None)])]),
])

def test_html_rows_keep_column_order_and_pad_colspan():
    assert html_table_rows(TABLE) == [
        ["Κονδύλι", "31.12.2024", "31.12.2023"],
        ["Κύκλος εργασιών", "1.146.865,95", "900,00"],
        ["Σύνολο", "", "5 & 6"],
    ]

def test_tables_found_inside_groups_with_page_index():
    tables = marker_tables(DOC)
    assert [i for i, _ in tables] == [1]
    assert tables[0][1][1] == ["Κύκλος εργασιών", "1.146.865,95", "900,00"]

def test_page_texts_strip_markup_per_page():
    texts = marker_page_texts(DOC, 3)
    assert texts[0] == "Ισολογισμός & αποτελέσματα"
    assert "1.146.865,95" in texts[1] and "<td>" not in texts[1]
    assert texts[2] == ""

def test_rowspan_keeps_later_cells_in_their_column():
    html = ("<table><tr><td rowspan=\"2\">Ενεργητικό</td><td>2024</td><td>2023</td></tr>"
            "<tr><td>10,00</td><td>20,00</td></tr></table>")
    assert html_table_rows(html) == [["Ενεργητικό", "2024", "2023"], ["", "10,00", "20,00"]]

def test_saved_marker_json_feeds_the_core_parser():
    import json
    from parsing_benchmark import OUT, ROOT, marker_extract
    stem = "54414421000_2024_isologismos"
    data = json.loads((OUT / f"{stem}.marker.json").read_text())
    got = marker_extract(ROOT / f"extractor/fixtures/{stem}.pdf", data)
    assert got["fiscal_year"] == 2024 and got["figures"]["turnover"]["value"] == 339878.25

def test_marker_geo_refuses_a_blank_page_even_with_a_hallucinated_table():
    from parsing_benchmark import ROOT, marker_extract
    html = "<table><tr><td>Κύκλος εργασιών</td><td>31.12.2024</td></tr><tr><td>Κύκλος εργασιών</td><td>1.000,00</td></tr></table>"
    data = dict(children=[dict(block_type="Page", html="", children=[dict(block_type="Table", html=html, children=None)])])
    got = marker_extract(ROOT / "extractor/fixtures/_synthetic_no_text.pdf", data, use_geo=True)
    assert got["figures"] == {} and got["reason"] == "no_text_layer"

def test_short_row_does_not_leak_rowspan_into_later_rows():
    html = ("<table><tr><td>Κονδύλι</td><td>2024</td><td rowspan=\"2\">2023</td></tr>"
            "<tr><td>Σημείωση</td></tr>"
            "<tr><td>Κύκλος εργασιών</td><td>10,00</td><td>20,00</td></tr></table>")
    assert html_table_rows(html)[2] == ["Κύκλος εργασιών", "10,00", "20,00"]

def test_amount_spanning_several_columns_is_dropped_not_assigned():
    html = "<table><tr><td>Κύκλος εργασιών</td><td colspan=\"2\">1.000,00</td></tr></table>"
    assert html_table_rows(html) == [["Κύκλος εργασιών", "", ""]]

def test_text_layer_mode_never_takes_marker_text_for_a_blank_pdf():
    from parsing_benchmark import ROOT, marker_extract
    rows = "".join(f"<tr><td>Κύκλος εργασιών {i}</td><td>31.12.2024</td><td>9.999,00</td></tr>" for i in range(40))
    data = dict(children=[dict(block_type="Page", html="", children=[
        dict(block_type="Table", html=f"<table>{rows}</table>", children=None)])])
    blank = ROOT / "extractor/fixtures/_synthetic_no_text.pdf"
    for use_geo in (False, True):
        got = marker_extract(blank, data, use_geo=use_geo, ocr=False)
        assert got["figures"] == {} and got["reason"] == "no_text_layer"

def test_ocr_metric_keeps_sign_and_whole_tokens():
    from ocr_quality import numbers
    assert numbers("(1.234) -5.678 9.999") == numbers("-1.234 −5.678 9.999")
    assert numbers("1.234") != numbers("-1.234")
    assert "4.947.477" not in numbers("14.947.477,99")

def test_merged_label_with_digits_is_kept():
    html = ("<table><tr><td colspan=\"2\">Κύκλος εργασιών (1)</td><td>1.000,00</td></tr></table>")
    assert html_table_rows(html) == [["Κύκλος εργασιών (1)", "", "1.000,00"]]

def test_ocr_metric_keeps_sign_across_whitespace():
    from ocr_quality import numbers
    assert numbers("- 1.234") == numbers("( 1.234 )") == numbers("-1.234")
    assert numbers("- 1.234") != numbers("1.234")
    assert numbers("-\n31.12.2024") == numbers("-31.12.2024")

def test_spanning_amount_with_currency_text_is_dropped():
    for cell in ("1.000,00 €", "ποσό 1.000.000", "(12.345)", "250,50 ευρώ"):
        html = f"<table><tr><td>Κύκλος εργασιών</td><td colspan=\"2\">{cell}</td></tr></table>"
        assert html_table_rows(html) == [["Κύκλος εργασιών", "", ""]], cell
    html = "<table><tr><td colspan=\"2\">Σημ. 31.12.2024 (8)</td></tr></table>"
    assert html_table_rows(html) == [["Σημ. 31.12.2024 (8)", ""]]
