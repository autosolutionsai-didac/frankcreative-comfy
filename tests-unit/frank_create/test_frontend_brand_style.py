from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frank-create"
STYLES = FRONTEND / "src" / "styles.css"
FONTS = FRONTEND / "src" / "assets" / "fonts"


def test_frontend_uses_2026_frank_body_brand_fonts_and_palette():
    css = STYLES.read_text(encoding="utf-8")

    assert (FONTS / "Pitch-Semibold.woff2").is_file()
    assert (FONTS / "FoundersGroteskText-Light.woff2").is_file()
    assert (FONTS / "FoundersGroteskText-Regular.otf").is_file()
    assert (FONTS / "FoundersGroteskText-Semibold.otf").is_file()
    assert '@font-face' in css
    assert 'font-family: "Pitch"' in css
    assert 'font-family: "Founders Grotesk Text"' in css
    assert '--frank-original-pink: #ffb6a5' in css.lower()
    assert '--frank-black: #3f2a2d' in css.lower()
    assert '--frank-white: #ffffff' in css.lower()
    assert '--font-brand: "Pitch"' in css
    assert '--font-body: "Founders Grotesk Text"' in css


def test_frontend_exposes_concern_category_colours_as_badge_tokens():
    css = STYLES.read_text(encoding="utf-8").lower()

    assert "--concern-acid-primary: #69e9d2" in css
    assert "--concern-barrier-primary: #4fa6e1" in css
    assert "--concern-firm-primary: #ffb2bc" in css
    assert "--concern-caffeinated-primary: #ffb6a5" in css
    assert "--concern-anti-ageing-primary: #a0acff" in css
    assert "--concern-tan-primary: #f4c3ab" in css
    assert "--concern-relax-primary: #869ab7" in css
