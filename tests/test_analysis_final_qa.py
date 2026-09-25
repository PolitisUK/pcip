from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def test_researcher_language_does_not_imply_automatic_methodological_conclusions():
    public_home = Path("app/templates/public_home.html").read_text(encoding="utf-8")
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app/templates").glob("*.html")
    )

    assert "Findings emerge" not in public_home
    assert "Emerging insight" not in public_home
    assert "Follow emerging themes" not in public_home
    assert "Researchers develop findings" in public_home
    assert "Provisional interpretation" in public_home
    assert "Chronology is not causation" in templates
    assert "neither frequency nor co-occurrence proves importance" in templates
    assert "They never become researcher-authored analysis automatically" in templates


def test_methodological_objects_remain_explicitly_distinct_in_researcher_ui():
    themes = Path("app/templates/research_themes.html").read_text(encoding="utf-8")
    findings = Path("app/templates/research_findings.html").read_text(encoding="utf-8")
    relationships = Path("app/templates/research_relationships.html").read_text(
        encoding="utf-8"
    )

    assert "Three distinct analytical records" in themes
    assert "counts do not establish importance" in themes
    assert "It is not a code, theme, memo or AI suggestion" in findings
    assert "Contradictory material remains part of the analytical record" in findings
    assert "explicit researcher assertions" in relationships
    assert "not automatically inferred links" in relationships


def test_workspace_navigation_is_compact_accessible_and_keeps_destinations():
    navigation = Path("app/templates/_workspace_nav.html").read_text(encoding="utf-8")
    css = Path("app/static/app.css").read_text(encoding="utf-8")
    base = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert '<nav class="workspace-nav" aria-label="Research workspace">' in navigation
    assert 'class="workspace-nav__label"' not in navigation
    assert 'class="workspace-nav__heading"' not in navigation
    assert navigation.count('class="workspace-nav__group" role="group"') == 3
    assert navigation.count('role="group" aria-label=') == 3
    assert ">Review sources<" not in navigation
    assert ">Develop analysis<" not in navigation
    assert ">Review &amp; share<" not in navigation
    for label in (
        "Overview",
        "Entries",
        "Participants",
        "Evidence",
        "Coded passages",
        "Codes &amp; themes",
        "Compare cases",
        "Over time",
        "Combine codes",
        "AI suggestions",
        "Ask AI",
        "History",
        "Export",
    ):
        assert navigation.count(f">{label}</a>") == 1
        assert f">{label}</a>" in navigation
    nav_start = css.index(".workspace-nav {")
    nav_rule = css[nav_start : css.index("}", nav_start)]
    link_rule = css[
        css.index(".workspace-nav > a,") : css.index(
            "}", css.index(".workspace-nav > a,")
        )
    ]
    assert "flex-wrap: nowrap;" in nav_rule
    assert "overflow-x: auto;" in nav_rule
    assert "white-space: nowrap;" in link_rule
    assert ".workspace-nav a:focus-visible" in css
    assert "min-height: 40px;" in link_rule
    assert ".workspace-nav__heading" not in css
    assert "/static/app.css?v={{ version }}-ux-v6" in base


def test_workspace_navigation_marks_each_active_destination_once():
    environment = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(("html",)),
    )
    navigation = environment.get_template("_workspace_nav.html")
    destinations = {
        "overview": "Overview",
        "entries": "Entries",
        "participants": "Participants",
        "evidence": "Evidence",
        "coding": "Coded passages",
        "themes": "Codes &amp; themes",
        "matrices": "Compare cases",
        "longitudinal": "Over time",
        "queries": "Combine codes",
        "analysis": "AI suggestions",
        "ask_ai": "Ask AI",
        "audit": "History",
        "export": "Export",
    }

    for section, label in destinations.items():
        rendered = navigation.render(project={"id": 17}, workspace_section=section)
        assert rendered.count('aria-current="page"') == 1
        assert f'aria-current="page">{label}</a>' in rendered
