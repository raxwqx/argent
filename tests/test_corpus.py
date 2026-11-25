from argent.bench import render_table, run_bench, summarise
from argent.corpus import FAMILIES, build_corpus, write_corpus


def test_corpus_is_deterministic():
    first = build_corpus(per_family=1)
    second = build_corpus(per_family=1)
    assert [c.source for c in first] == [c.source for c in second]
    assert [c.name for c in first] == [c.name for c in second]


def test_different_seed_changes_programs():
    first = build_corpus(per_family=1, seed=1)
    second = build_corpus(per_family=1, seed=2)
    assert [c.source for c in first] != [c.source for c in second]


def test_every_family_is_present():
    corpus = build_corpus(per_family=1)
    assert {c.family for c in corpus} == set(FAMILIES)


def test_per_family_mapping():
    corpus = build_corpus(per_family={"eq": 3, "xor": 1})
    counts = {}
    for item in corpus:
        counts[item.family] = counts.get(item.family, 0) + 1
    assert counts["eq"] == 3
    assert counts["xor"] == 1
    assert counts["hash"] == FAMILIES["hash"][2]


def test_every_program_assembles_and_has_a_win_label():
    for item in build_corpus(per_family=1):
        program = item.program()
        assert "win" in program.labels
        assert item.goal_index() == program.label("win")
        assert len(program) > 0


def test_input_sizes_match_family_specs():
    for item in build_corpus(per_family=1):
        expected = FAMILIES[item.family][1]
        assert item.input_size == expected


def test_write_corpus(tmp_path):
    paths = write_corpus(tmp_path / "corpus", per_family=1)
    assert len(paths) == len(FAMILIES)
    for path in paths:
        assert path.suffix == ".sasm"
        assert path.read_text(encoding="utf-8").startswith("# ")
    assert len(list((tmp_path / "corpus").glob("*.sasm"))) == len(FAMILIES)


def test_bench_runs_a_small_corpus():
    cases = run_bench(per_family=1)
    assert len(cases) == len(FAMILIES)
    summary = summarise(cases)
    assert summary["total"]["cases"] == len(FAMILIES)
    assert summary["total"]["solved"] == len(FAMILIES) - 1  # impossible never solves
    assert summary["total"]["verified"] == summary["total"]["solved"]


def test_bench_table_is_plain_text():
    cases = run_bench(per_family=1)
    table = render_table(summarise(cases))
    assert "family" in table
    assert "total" in table
    assert "|" not in table
    assert all(ord(ch) < 128 for ch in table)


def test_summary_groups_by_family():
    summary = summarise(run_bench(per_family=1))
    families = {row["family"] for row in summary["families"]}
    assert families == set(FAMILIES)
    for row in summary["families"]:
        assert row["cases"] == 1
