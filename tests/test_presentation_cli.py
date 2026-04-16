from src.core.presentation import cli


def test_visible_len_counts_cjk_as_double_width() -> None:
    assert cli._visible_len("华尔街") == 6
    assert cli._visible_len(f"{cli.FG_BLUE}华尔街{cli.RESET}") == 6


def test_wrap_breaks_cjk_text_without_spaces() -> None:
    wrapped = cli._wrap("华尔街深渊账本", 6)

    assert wrapped == ["华尔街", "深渊账", "本"]


def test_box_header_stays_within_requested_width() -> None:
    box = cli._box("这是一个很长很长的标题", ["内容"], width=20)
    for line in box.splitlines():
        assert cli._visible_len(line) == 20
