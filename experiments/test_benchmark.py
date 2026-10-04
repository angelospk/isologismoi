from parsing_benchmark import score
def record(year=2024,figures=None):
 return dict(status="parsed",fiscal_year=year,currency="EUR",unit_multiplier=1,figures=figures or {})
def test_correct_value_in_wrong_year_is_not_anchored():
 gold=record(figures={"turnover":{"value":100}})
 got=record(2023,{"turnover":{"value":100}})
 assert score(gold,got)["correct_fields"]==1
 assert score(gold,got)["anchored_correct_fields"]==0
def test_missing_zero_is_not_an_extracted_zero():
 gold=record(figures={"net_profit":{"value":0}})
 m=score(gold,record())
 assert m["missing_fields"]==["net_profit"] and m["correct_fields"]==0
def test_locale_string_is_rejected_as_decimal_value():
 gold=record(figures={"turnover":{"value":1146865.95}})
 got=record(figures={"turnover":{"value":"1.146.865,95"}})
 assert score(gold,got)["wrong_fields"]==["turnover"]
def test_numbers_on_refusal_gold_are_not_silently_accepted():
 gold=dict(status="unparseable",figures={})
 got=record(figures={"turnover":{"value":100}})
 m=score(gold,got)
 assert m["policy_violation"] and m["unsupported_fields"]==["turnover"]

