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
