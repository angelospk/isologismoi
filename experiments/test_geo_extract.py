from geo_extract import extract_pages


def w(text, x0, top, width=40, height=8):
    return dict(text=text, x0=x0, x1=x0 + width, top=top, bottom=top + height)


def line(top, label, cells, xs=(300, 400, 500, 600)):
    out = [w(t, 20 + i * 45, top) for i, t in enumerate(label.split())]
    return out + [w(c, x, top) for c, x in zip(cells, xs) if c is not None]


def page(*lines, text=None):
    words = [x for ln in lines for x in ln]
    return dict(width=700, height=900, words=words), text or " ".join(x["text"] for x in words)


def run(*pages_):
    return extract_pages([p for p, _ in pages_], [t for _, t in pages_])


def dual_scope(rows):
    return page(
        [w("Όμιλος", 350, 90), w("Εταιρεία", 550, 90)],
        [w("31.12.2024", 300, 100), w("31.12.2023", 400, 100), w("31.12.2024", 500, 100), w("31.12.2023", 600, 100)],
        *rows)


def test_dual_scope_reads_the_company_current_year_column():
    out = run(dual_scope([line(120, "Κύκλος εργασιών", ["900,00", "800,00", "700,00", "600,00"])]))
    assert out["figures"]["turnover"]["value"] == 700
    assert out["figures"]["turnover"]["scope"] == "company"


def test_four_columns_without_scope_labels_are_not_guessed():
    p = page([w("31.12.2024", 300, 100), w("31.12.2023", 400, 100), w("31.12.2024", 500, 100), w("31.12.2023", 600, 100)],
             line(120, "Κύκλος εργασιών", ["900,00", "800,00", "700,00", "600,00"]))
    assert "turnover" not in run(p)["figures"]


def test_thousands_separated_integer_is_an_amount_not_a_note_reference():
    p = page([w("2024", 300, 100), w("2023", 400, 100)], line(120, "Κύκλος εργασιών", ["8.411", "7.000"]))
    assert run(p)["figures"]["turnover"]["value"] == 8411


def test_extra_dash_cells_collide_and_the_row_is_refused():
    p = page([w("2024", 300, 100), w("2023", 400, 100)],
             line(120, "Πωλήσεις", ["-", "-", "(174)"], xs=(290, 330, 410)))
    assert "turnover" not in run(p)["figures"]


def test_note_number_between_label_and_columns_is_ignored():
    p = page([w("2024", 300, 100), w("2023", 400, 100)], line(120, "Κύκλος εργασιών", ["5", "1.000,00", "900,00"], xs=(200, 300, 400)))
    assert run(p)["figures"]["turnover"]["value"] == 1000


def test_dash_in_the_target_column_is_missing_not_zero():
    p = page([w("2024", 300, 100), w("2023", 400, 100)], line(120, "Κύκλος εργασιών", ["-", "5.000"]))
    assert "turnover" not in run(p)["figures"]


def test_page_in_thousands_multiplies_integer_amounts():
    p = page([w("2024", 300, 100), w("2023", 400, 100)], line(120, "Κύκλος εργασιών", ["205.619", "174.063"]),
             text="Όλα τα ποσά είναι σε χιλιάδες ευρώ 2024 2023 Κύκλος εργασιών 205.619 174.063")
    out = run(p)
    assert out["figures"]["turnover"]["value"] == 205619000 and out["unit_multiplier"] == 1000


def test_thousands_elsewhere_and_no_cents_leaves_the_unit_unknown():
    statement = page([w("2024", 300, 100), w("2023", 400, 100)], line(120, "Κύκλος εργασιών", ["205.619", "174.063"]))
    note = page([w("x", 20, 100)], text="Τα ποσά της σημείωσης σε χιλιάδες ευρώ")
    assert "turnover" not in run(statement, note)["figures"]


def test_latin_homoglyphs_and_two_line_labels_still_match():
    p = page([w("2024", 300, 100), w("2023", 400, 100)],
             line(120, "ΣΥΝΟΛΟ ENEPΓHTIKOY", ["1.000,00", "900,00"]),
             line(140, "ΚΕΡΔΗ/(ΖΗΜΙΕΣ) ΠΡΟ ΦΟΡΩΝ", [None, None]),
             line(152, "ΕΙΣΟΔΗΜΑΤΟΣ", ["50,00", "40,00"]))
    figures = run(p)["figures"]
    assert figures["total_assets"]["value"] == 1000 and figures["pre_tax_profit"]["value"] == 50


def test_balance_sheet_that_does_not_balance_is_dropped():
    p = page([w("2024", 300, 100), w("2023", 400, 100)],
             line(120, "Σύνολο ενεργητικού", ["1.000,00", "900,00"]),
             line(140, "Σύνολο καθαρής θέσης", ["300,00", "200,00"]),
             line(160, "Σύνολο υποχρεώσεων", ["600,00", "700,00"]))
    assert "total_assets" not in run(p)["figures"]


def two_cols(top=100):
    return [w("2024", 300, top), w("2023", 400, top)]


def test_cents_on_a_page_of_a_thousands_document_are_not_proof_of_euros():
    statement = page(two_cols(), line(120, "Κύκλος εργασιών", ["205,62", "174,06"]))
    other = page([w("x", 20, 100)], text="Όλα τα ποσά είναι σε χιλιάδες ευρώ")
    assert "turnover" not in run(other, statement)["figures"]


def test_page_printed_in_cents_throughout_is_in_euros_despite_a_thousands_mention_elsewhere():
    rows = [line(120 + 20 * i, label, [f"{i + 1}.000,00", "900,00"])
            for i, label in enumerate(["Κύκλος εργασιών", "Κόστος πωλήσεων", "Μικτό αποτέλεσμα"])]
    statement = page(two_cols(), *rows)
    other = page([w("x", 20, 100)], text="Τα ποσά της σημείωσης σε χιλιάδες ευρώ")
    assert run(other, statement)["figures"]["turnover"]["value"] == 1000


def test_millions_are_refused():
    p = page(two_cols(), line(120, "Κύκλος εργασιών", ["205,6", "174,1"]),
             text="Ποσά σε εκατομμύρια ευρώ 2024 2023 Κύκλος εργασιών")
    assert "turnover" not in run(p)["figures"]


def test_cents_in_a_thousands_statement_are_refused():
    p = page(two_cols(), line(120, "Κύκλος εργασιών", ["205,62", "174,06"]),
             text="Όλα τα ποσά είναι σε χιλιάδες ευρώ")
    assert "turnover" not in run(p)["figures"]


def test_unlabelled_two_columns_on_a_group_page_are_not_read_as_company():
    p = page([w("Κατάσταση", 20, 60), w("αποτελεσμάτων", 70, 60), w("Ομίλου", 150, 60)],
             two_cols(), line(120, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert "turnover" not in run(p)["figures"]


def test_header_is_not_carried_onto_a_group_page():
    first = page(two_cols(), line(120, "Σύνολο ενεργητικού", ["1.000,00", "900,00"]))
    second = page([w("Ενοποιημένη", 20, 60), w("κατάσταση", 100, 60)],
                  line(120, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert "turnover" not in run(first, second)["figures"]


def test_header_is_carried_onto_the_next_plain_page():
    first = page(two_cols(), line(120, "Σύνολο ενεργητικού", ["1.000,00", "900,00"]))
    second = page(line(120, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert run(first, second)["figures"]["turnover"]["value"] == 900


def test_labelled_scope_header_carries_only_onto_full_rows():
    first = dual_scope([line(120, "Σύνολο ενεργητικού", ["1,00", "2,00", "3,00", "4,00"])])
    full = page(line(120, "Κύκλος εργασιών", ["900,00", "800,00", "700,00", "600,00"]))
    partial = page(line(120, "Κύκλος εργασιών", ["900,00", "800,00"], xs=(500, 600)))
    assert run(first, full)["figures"]["turnover"]["value"] == 700
    assert "turnover" not in run(first, partial)["figures"]


def test_right_aligned_amounts_offset_from_year_headers_are_read_in_order():
    p = page(two_cols(), line(120, "Κύκλος εργασιών", ["339.878,25", "432.345,08"], xs=(335, 440)))
    assert run(p)["figures"]["turnover"]["value"] == 339878.25


def test_full_row_whose_cells_are_nearer_the_wrong_columns_is_refused():
    p = page(two_cols(), line(120, "Κύκλος εργασιών", ["900,00", "800,00"], xs=(380, 400)))
    assert "turnover" not in run(p)["figures"]


def test_amount_midway_between_columns_is_refused():
    p = page(two_cols(), line(120, "Κύκλος εργασιών", ["900,00"], xs=(350,)))
    assert "turnover" not in run(p)["figures"]


def test_dash_row_label_is_not_given_to_the_next_unlabelled_amounts():
    p = page(two_cols(), line(120, "Κύκλος εργασιών", ["-", "-"]), line(132, "", ["500,00", "400,00"]))
    assert "turnover" not in run(p)["figures"]


def test_distant_label_line_is_not_joined():
    p = page(two_cols(), line(120, "ΚΕΡΔΗ/(ΖΗΜΙΕΣ) ΠΡΟ ΦΟΡΩΝ", [None, None]),
             line(200, "ΕΙΣΟΔΗΜΑΤΟΣ", ["50,00", "40,00"]))
    assert "pre_tax_profit" not in run(p)["figures"]


def test_low_confidence_ocr_amount_is_refused():
    row = line(120, "Κύκλος εργασιών", ["900,00", "800,00"])
    row[-2]["score"] = 0.80
    assert "turnover" not in run(page(two_cols(), row))["figures"]


def test_low_confidence_ocr_year_does_not_make_a_header():
    header = two_cols()
    header[0]["score"] = 0.5
    assert "turnover" not in run(page(header, line(120, "Κύκλος εργασιών", ["900,00", "800,00"])))["figures"]


def test_carried_header_does_not_override_a_millions_page():
    # Page 1 prints cents throughout, so its own unit is euros.
    first = page(two_cols(), *[line(120 + 20 * i, label, ["1.000,00", "900,00"])
                               for i, label in enumerate(["Σύνολο ενεργητικού", "Ταμείο", "Αποθέματα"])])
    assert run(first)["unit_multiplier"] == 1
    second = page(line(120, "Κύκλος εργασιών", ["205,6", "174,1"]), text="Ποσά σε εκατομμύρια ευρώ Κύκλος εργασιών")
    assert "turnover" not in run(first, second)["figures"]


def test_header_carries_one_page_only():
    first = page(two_cols(), line(120, "Σύνολο ενεργητικού", ["1.000,00", "900,00"]))
    second = page(line(120, "Κόστος πωλήσεων", ["500,00", "400,00"]))
    third = page(line(120, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert "turnover" not in run(first, second, third)["figures"]


def test_rejected_header_invalidates_the_previous_columns():
    good = two_cols(100)
    bad = [w("2023", 300, 140, ), w("2022", 400, 140)]
    bad[0]["score"] = 0.5
    p = page(good, line(120, "Σύνολο ενεργητικού", ["1.000,00", "900,00"]), bad,
             line(160, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert "turnover" not in run(p)["figures"]


def test_low_confidence_scope_label_refuses_the_table():
    scope = [w("Όμιλος", 350, 90), w("Εταιρεία", 550, 90)]
    scope[1]["score"] = 0.6
    p = page(scope, [w("31.12.2024", 300, 100), w("31.12.2023", 400, 100), w("31.12.2024", 500, 100), w("31.12.2023", 600, 100)],
             line(120, "Κύκλος εργασιών", ["900,00", "800,00", "700,00", "600,00"]))
    assert "turnover" not in run(p)["figures"]


def test_low_confidence_single_scope_label_does_not_fall_back_to_single():
    scope = [w("Εταιρεία", 350, 90)]
    scope[0]["score"] = 0.6
    p = page(scope, two_cols(), line(120, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert "turnover" not in run(p)["figures"]


def test_garbled_low_confidence_replacement_header_invalidates_the_columns():
    for second_year in ("2028", "202Z"):
        bad = [w("2023", 300, 140), w(second_year, 400, 140)]
        bad[1]["score"] = 0.5
        p = page(two_cols(100), line(120, "Σύνολο ενεργητικού", ["1.000,00", "900,00"]), bad,
                 line(160, "Κύκλος εργασιών", ["900,00", "800,00"]))
        assert "turnover" not in run(p)["figures"], second_year


def test_low_confidence_amount_row_is_not_mistaken_for_a_header():
    row = line(140, "Υποχρεώσεις παροχών", ["50.554", "43.861"])
    row[-1]["score"] = 0.93
    p = page(two_cols(100), row, line(160, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert run(p)["figures"]["turnover"]["value"] == 900


def test_group_target_reads_the_group_column_and_company_target_ignores_a_group_page():
    dual = dual_scope([line(120, "Κύκλος εργασιών", ["900,00", "800,00", "700,00", "600,00"])])
    assert extract_pages([dual[0]], [dual[1]], target_scope="group")["figures"]["turnover"]["value"] == 900
    group_page = page([w("Ενοποιημένη", 20, 60), w("κατάσταση", 100, 60)], two_cols(),
                      line(120, "Κύκλος εργασιών", ["900,00", "800,00"]))
    assert extract_pages([group_page[0]], [group_page[1]], target_scope="group")["figures"]["turnover"]["value"] == 900
    assert "turnover" not in run(group_page)["figures"]
