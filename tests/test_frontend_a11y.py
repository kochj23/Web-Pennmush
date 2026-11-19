"""
Accessibility of the served client: labelled command input, a polite live
region for game text, keyboard-reachable controls, visible focus styles and
prefers-reduced-motion. Checks the HTML/CSS/JS exactly as the server serves it.
"""
from html.parser import HTMLParser

import pytest


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []  # (tag, attrs dict)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.fixture
async def page(app_client):
    r = await app_client.get("/")
    assert r.status_code == 200
    p = _Collect()
    p.feed(r.text)
    return p.elements


def _by_id(elements, id_):
    return next(a for t, a in elements if a.get("id") == id_)


async def test_command_input_is_labelled(page):
    labels = {a.get("for") for t, a in page if t == "label"}
    assert "command-input" in labels
    inp = _by_id(page, "command-input")
    assert inp.get("aria-describedby") == "input-help"
    _by_id(page, "input-help")


async def test_game_output_is_a_polite_live_region(page):
    out = _by_id(page, "output")
    assert out.get("aria-live") == "polite"
    assert out.get("role") == "log"
    assert out.get("aria-label")
    assert out.get("tabindex") == "0"  # scrollable with the keyboard


async def test_status_and_errors_are_announced(page):
    assert _by_id(page, "connection-status").get("aria-live") == "polite"
    assert _by_id(page, "login-error").get("role") == "alert"
    assert _by_id(page, "register-error").get("role") == "alert"


async def test_every_form_field_has_a_label(page):
    labels = {a.get("for") for t, a in page if t == "label"}
    for tag, attrs in page:
        if tag in ("input", "select", "textarea") and attrs.get("type") != "hidden":
            assert attrs.get("id") in labels or attrs.get("aria-label"), attrs


async def test_controls_are_native_buttons_with_explicit_type(page):
    buttons = [a for t, a in page if t == "button"]
    assert buttons
    assert all(a.get("type") in ("button", "submit") for a in buttons), buttons
    # No click targets built from non-focusable elements in the markup.
    assert not [a for t, a in page if t in ("div", "span") and "data-cmd" in a]


async def test_dialog_and_tabs_semantics(page):
    modal = _by_id(page, "login-modal")
    assert modal.get("role") == "dialog" and modal.get("aria-modal") == "true"
    assert _by_id(page, modal["aria-labelledby"])
    tabs = [a for t, a in page if a.get("role") == "tab"]
    assert len(tabs) == 2
    for tab in tabs:
        assert tab.get("aria-controls") and tab.get("aria-selected") in ("true", "false")
        assert _by_id(page, tab["aria-controls"]).get("role") == "tabpanel"


async def test_skip_link_targets_the_command_input(page):
    assert any(t == "a" and a.get("href") == "#command-input" for t, a in page)


async def test_css_has_focus_styles_and_reduced_motion(app_client):
    css = (await app_client.get("/static/css/style.css")).text
    assert ":focus-visible" in css
    assert "outline: 3px solid" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    reduced = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "transition-duration" in reduced and "animation-duration" in reduced


async def test_dynamic_controls_are_keyboard_reachable(app_client):
    ui = (await app_client.get("/static/js/ui.js")).text
    roommap = (await app_client.get("/static/js/roommap.js")).text
    app_js = (await app_client.get("/static/js/app.js")).text
    assert "createElement('button')" in ui and ".onclick" not in ui  # exits are real buttons
    assert "aria-selected" in ui
    assert "setAttribute('tabindex', '0')" in roommap and "'keydown'" in roommap
    assert "ArrowRight" in app_js  # tab list arrow-key navigation
