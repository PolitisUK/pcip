from pathlib import Path


def test_study_analysis_navigation_opens_project_workspace():
    template = Path("app/templates/study_detail.html").read_text(encoding="utf-8")

    assert 'href="/projects/{{ project.id }}/workspace/analysis">Analysis</a>' in template
    assert 'href="#analysis">Analysis</a>' not in template


def test_projects_page_analysis_control_opens_project_workspace():
    template = Path("app/templates/projects.html").read_text(encoding="utf-8")

    assert 'href="/projects/{{ p.id }}/workspace/analysis">Analysis</a>' in template
    assert 'href="#analysis">Analysis</a>' not in template
