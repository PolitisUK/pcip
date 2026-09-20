from pathlib import Path


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


def test_workspace_navigation_uses_semantic_groups_and_keeps_destinations():
    navigation = Path("app/templates/_workspace_nav.html").read_text(encoding="utf-8")
    css = Path("app/static/app.css").read_text(encoding="utf-8")

    assert 'class="workspace-nav__label"' not in navigation
    assert navigation.count('class="workspace-nav__group" role="group"') == 3
    assert navigation.count('class="workspace-nav__heading" id=') == 3
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
        "History",
        "Export",
    ):
        assert f">{label}</a>" in navigation
    assert ".workspace-nav__links {" in css
    assert ".workspace-nav__heading {" in css
    heading_rule = css[
        css.index(".workspace-nav__heading {") : css.index(
            "}", css.index(".workspace-nav__heading {")
        )
    ]
    assert "text-transform: uppercase" not in heading_rule
    assert ".workspace-nav__links { flex-wrap: nowrap; }" in css
