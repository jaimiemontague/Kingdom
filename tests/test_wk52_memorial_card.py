"""WK52 memorial card unit tests."""

from game.ui.memorial_card import MemorialCard, MemorialRecord, _generate_epitaph


def test_memorial_record_captures_fields():
    r = MemorialRecord("h1", "Aria", "warrior", 7, 25, 3, 800)
    assert r.level == 7
    epitaph = _generate_epitaph(r)
    assert isinstance(epitaph, str) and len(epitaph) > 10


def test_epitaph_high_kills():
    r = MemorialRecord("h2", "Bran", "ranger", 4, 22, 0, 100)
    assert "22" in _generate_epitaph(r)


def test_memorial_card_show_hide():
    card = MemorialCard()
    r = MemorialRecord("h3", "Cal", "mage", 3, 5, 2, 200)
    assert not card.visible
    card.show(r)
    assert card.visible
    card.hide()
    assert not card.visible
    assert card._record is None
